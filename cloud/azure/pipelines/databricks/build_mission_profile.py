"""Build the weekly mission-selection profile from canonical ready Trips.

The pure helpers are intentionally Spark-free for deterministic unit tests. ``run`` is
the Databricks entry point: it reads the completed source week, writes full Gold
history, and upserts one latest profile document per user to Cosmos DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

LOW_CARBON_MODES = {"walk", "bike", "bus", "rail"}
TRANSIT_MODES = {"bus", "rail"}
SHORT_CAR_MAX_DISTANCE_M = 2000.0
PROFILE_VERSION = "mission-profile-v1"

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)
GOLD_MISSION_PROFILE_PATH = os.environ.get(
    "CANOPY_GOLD_MISSION_PROFILE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_profile/",
)
GOLD_WEEKLY_USER_PATH = os.environ.get(
    "CANOPY_GOLD_WEEKLY_USER_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/",
)
COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_PROFILE_CONTAINER = os.environ.get(
    "CANOPY_COSMOS_MISSION_PROFILE_CONTAINER", "mission-profiles"
)


def compute_last_completed_week(reference_date=None, timezone_name=None):
    tz_name = timezone_name or os.environ.get("CANOPY_CAMPAIGN_TIMEZONE", "Asia/Seoul")
    ref = reference_date or datetime.now(ZoneInfo(tz_name)).date()
    this_monday = ref - timedelta(days=ref.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday
    return start.isoformat(), end.isoformat()


def _segment_mode(segment: Mapping[str, Any]) -> str | None:
    value = segment.get("model_prediction")
    return value.lower() if isinstance(value, str) and value.lower() in LOW_CARBON_MODES | {"car"} else None


def derive_trip_primary_mode(trip: Mapping[str, Any]) -> tuple[str | None, float | None, str | None]:
    """Return (primary_mode, total_distance_m, invalid_reason).

    A Trip primary mode is the unique mode with the greatest summed segment distance.
    We intentionally do not invent a tie-break. Missing/zero distance or a top-distance
    tie makes the Trip unusable for mission-profile denominators.
    """
    segments = trip.get("segments")
    if not isinstance(segments, list) or not segments:
        return None, None, "segments_missing"

    distance_by_mode: dict[str, float] = defaultdict(float)
    total = 0.0
    for segment in segments:
        if not isinstance(segment, Mapping):
            return None, None, "invalid_segment"
        mode = _segment_mode(segment)
        distance = segment.get("distance_m")
        if mode is None or isinstance(distance, bool):
            return None, None, "segment_mode_or_distance_missing"
        try:
            distance = float(distance)
        except (TypeError, ValueError):
            return None, None, "segment_mode_or_distance_missing"
        if distance <= 0:
            return None, None, "non_positive_distance"
        distance_by_mode[mode] += distance
        total += distance

    if total <= 0 or not distance_by_mode:
        return None, None, "non_positive_distance"

    max_distance = max(distance_by_mode.values())
    winners = [mode for mode, distance in distance_by_mode.items() if abs(distance - max_distance) < 1e-9]
    if len(winners) != 1:
        return None, total, "primary_mode_tie"
    return winners[0], total, None


def build_profile_from_trips(
    trips: Iterable[Mapping[str, Any]],
    *,
    user_id: str,
    campaign_id: str,
    source_week_start: str,
    source_week_end: str,
    previous_mission: Mapping[str, Any] | None = None,
    carbon_change_rate: float | None = None,
) -> dict[str, Any]:
    valid_trip_count = 0
    car_count = 0
    short_car_count = 0
    transit_count = 0
    low_carbon_count = 0
    invalid_trip_count = 0
    invalid_reasons: dict[str, int] = defaultdict(int)

    for trip in trips:
        mode, distance_m, invalid_reason = derive_trip_primary_mode(trip)
        if invalid_reason:
            invalid_trip_count += 1
            invalid_reasons[invalid_reason] += 1
            continue
        valid_trip_count += 1
        if mode == "car":
            car_count += 1
            if distance_m is not None and distance_m <= SHORT_CAR_MAX_DISTANCE_M:
                short_car_count += 1
        if mode in TRANSIT_MODES:
            transit_count += 1
        if mode in LOW_CARBON_MODES:
            low_carbon_count += 1

    car_ratio = (car_count / valid_trip_count) if valid_trip_count else None
    short_car_share = (short_car_count / car_count) if car_count else None

    # A zero-car user can legitimately have short_car_share=null while still being a
    # fully usable low-carbon profile. No valid Trip, however, means collecting.
    status = "ready" if valid_trip_count > 0 and car_ratio is not None else "collecting"

    previous = previous_mission or {}
    profile: dict[str, Any] = {
        "type": "mission_profile",
        "profile_version": PROFILE_VERSION,
        "profile_status": status,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "source_week_start": source_week_start,
        "source_week_end": source_week_end,
        "valid_trip_count": valid_trip_count,
        "invalid_trip_count": invalid_trip_count,
        "invalid_trip_reasons": dict(sorted(invalid_reasons.items())),
        "car_primary_trip_count": car_count,
        "car_ratio": car_ratio,
        "short_car_trip_count": short_car_count,
        "short_car_share": short_car_share,
        "transit_primary_trip_count": transit_count,
        "low_carbon_trip_count": low_carbon_count,
        "carbon_change_rate": carbon_change_rate,
        "previous_mission_family": previous.get("mission_family"),
        "previous_target_count": previous.get("target_count"),
        "previous_achievement_rate": previous.get("achievement_rate"),
        "previous_mission_completed": previous.get("completed"),
    }
    fingerprint_source = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    profile["profile_hash"] = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return profile


def _iso_week_label(day_iso: str) -> str:
    day = datetime.fromisoformat(day_iso).date()
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _carbon_change_map(spark, campaign_id: str, source_week_start: str):
    """Return recent weekly carbon change per user when both weeks exist.

    Mission selection v1 does not use this value yet, but the WBS profile contract
    requires it and future policy versions may. Missing/zero previous totals stay null.
    """
    from pyspark.sql import functions as F

    source_day = datetime.fromisoformat(source_week_start).date()
    previous_start = (source_day - timedelta(days=7)).isoformat()
    current_week = _iso_week_label(source_week_start)
    previous_week = _iso_week_label(previous_start)
    try:
        weekly = spark.read.format("delta").load(GOLD_WEEKLY_USER_PATH).filter(
            (F.col("campaign_id") == campaign_id) & F.col("week").isin([previous_week, current_week])
        )
    except Exception:
        return {}

    values = {}
    for row in weekly.select("user_id", "week", "total_kg_co2e").collect():
        values.setdefault(row["user_id"], {})[row["week"]] = row["total_kg_co2e"]

    changes = {}
    for user_id, weeks in values.items():
        current = weeks.get(current_week)
        previous = weeks.get(previous_week)
        if current is None or previous is None or float(previous) <= 0:
            changes[user_id] = None
        else:
            changes[user_id] = (float(current) - float(previous)) / float(previous)
    return changes


def _load_previous_assignments(container, campaign_id: str, source_week_start: str):
    query = (
        "SELECT * FROM c WHERE c.type = 'mission_assignment' "
        "AND c.campaign_id = @campaign_id AND c.week_start = @week_start"
    )
    params = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@week_start", "value": source_week_start},
    ]
    return {
        item["user_id"]: item
        for item in container.query_items(query=query, parameters=params, enable_cross_partition_query=True)
    }


def _cosmos_clients():
    if not COSMOS_ENDPOINT:
        return None, None
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    profile_container = db.get_container_client(COSMOS_PROFILE_CONTAINER)
    assignments = db.get_container_client(
        os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")
    )
    return profile_container, assignments


def _latest_profile_document(profile: Mapping[str, Any]) -> dict[str, Any]:
    campaign_id = str(profile["campaign_id"])
    user_id = str(profile["user_id"])
    return {
        **profile,
        "id": f"mission-profile-latest:{campaign_id}:{user_id}",
        "pk": f"{campaign_id}:{user_id}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def run(campaign_id: str, source_week_start: str, source_week_end: str):
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F
    from pyspark.sql.types import BooleanType, DoubleType, IntegerType, MapType, StringType, StructField, StructType

    spark = SparkSession.builder.getOrCreate()
    raw = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH).filter(
        (F.col("campaign_id") == campaign_id)
        & (F.col("status") == "ready")
        & (F.col("ended_at") >= source_week_start)
        & (F.col("ended_at") < source_week_end)
    )
    w = Window.partitionBy("trip_id").orderBy(F.col("updated_at").desc())
    raw = raw.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")

    profile_container, assignment_container = _cosmos_clients()
    previous_by_user = (
        _load_previous_assignments(assignment_container, campaign_id, source_week_start)
        if assignment_container is not None
        else {}
    )

    # Mission profile is one row per user/week. Collecting each user's Trip structs is
    # acceptable for the MVP weekly batch and keeps the primary-mode rule identical to
    # the pure tested helper. Replace with native Spark expressions if volume requires.
    trip_struct = F.struct(*[F.col(name) for name in raw.columns])
    grouped = raw.groupBy("user_id").agg(F.collect_list(trip_struct).alias("trips"))
    rows = grouped.collect()
    carbon_change_by_user = _carbon_change_map(spark, campaign_id, source_week_start)
    profiles = []
    for row in rows:
        trips = [trip.asDict(recursive=True) for trip in row["trips"]]
        profile = build_profile_from_trips(
            trips,
            user_id=row["user_id"],
            campaign_id=campaign_id,
            source_week_start=source_week_start,
            source_week_end=source_week_end,
            previous_mission=previous_by_user.get(row["user_id"]),
            carbon_change_rate=carbon_change_by_user.get(row["user_id"]),
        )
        profiles.append(profile)
        if profile_container is not None:
            profile_container.upsert_item(_latest_profile_document(profile))

    if not profiles:
        print(f"[done] campaign_id={campaign_id} no ready Trips in source week; no profiles written")
        return []

    schema = StructType([
        StructField("type", StringType(), False),
        StructField("profile_version", StringType(), False),
        StructField("profile_status", StringType(), False),
        StructField("user_id", StringType(), False),
        StructField("campaign_id", StringType(), False),
        StructField("source_week_start", StringType(), False),
        StructField("source_week_end", StringType(), False),
        StructField("valid_trip_count", IntegerType(), False),
        StructField("invalid_trip_count", IntegerType(), False),
        StructField("invalid_trip_reasons", MapType(StringType(), IntegerType()), False),
        StructField("car_primary_trip_count", IntegerType(), False),
        StructField("car_ratio", DoubleType(), True),
        StructField("short_car_trip_count", IntegerType(), False),
        StructField("short_car_share", DoubleType(), True),
        StructField("transit_primary_trip_count", IntegerType(), False),
        StructField("low_carbon_trip_count", IntegerType(), False),
        StructField("carbon_change_rate", DoubleType(), True),
        StructField("previous_mission_family", StringType(), True),
        StructField("previous_target_count", IntegerType(), True),
        StructField("previous_achievement_rate", DoubleType(), True),
        StructField("previous_mission_completed", BooleanType(), True),
        StructField("profile_hash", StringType(), False),
    ])
    out = spark.createDataFrame(profiles, schema=schema)
    (
        out.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .partitionBy("campaign_id", "source_week_start")
        .save(GOLD_MISSION_PROFILE_PATH)
    )
    print(f"[done] campaign_id={campaign_id} profiles={len(profiles)} source_week={source_week_start}")
    return profiles


if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else None
    start = sys.argv[2] if len(sys.argv) > 2 else ""
    end = sys.argv[3] if len(sys.argv) > 3 else ""
    if not campaign:
        raise ValueError("campaign_id parameter required")
    if not start or not end:
        start, end = compute_last_completed_week()
    run(campaign, start, end)

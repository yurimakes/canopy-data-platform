"""Build weekly mission-selection profiles from canonical ready Trips."""
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
SUPPORTED_MODES = LOW_CARBON_MODES | {"car"}
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
    return (this_monday - timedelta(days=7)).isoformat(), this_monday.isoformat()


def _utc_week_bounds(source_week_start: str, source_week_end: str, timezone_name=None):
    tz_name = timezone_name or os.environ.get("CANOPY_CAMPAIGN_TIMEZONE", "Asia/Seoul")
    tz = ZoneInfo(tz_name)
    start_local = datetime.fromisoformat(source_week_start).replace(tzinfo=tz)
    end_local = datetime.fromisoformat(source_week_end).replace(tzinfo=tz)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def _segment_mode(segment: Mapping[str, Any]) -> str | None:
    value = segment.get("model_prediction")
    if not isinstance(value, str):
        return None
    value = value.lower()
    return value if value in SUPPORTED_MODES else None


def derive_trip_primary_mode(trip: Mapping[str, Any]) -> tuple[str | None, float | None, str | None]:
    """Use the unique mode with greatest summed segment distance; never invent a tie-break."""
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

    maximum = max(distance_by_mode.values())
    winners = [mode for mode, value in distance_by_mode.items() if abs(value - maximum) < 1e-9]
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
    valid = car = short_car = transit = low_carbon = invalid = 0
    invalid_reasons: dict[str, int] = defaultdict(int)

    for trip in trips:
        mode, distance_m, reason = derive_trip_primary_mode(trip)
        if reason:
            invalid += 1
            invalid_reasons[reason] += 1
            continue
        valid += 1
        if mode == "car":
            car += 1
            if distance_m is not None and distance_m <= SHORT_CAR_MAX_DISTANCE_M:
                short_car += 1
        if mode in TRANSIT_MODES:
            transit += 1
        if mode in LOW_CARBON_MODES:
            low_carbon += 1

    car_ratio = car / valid if valid else None
    short_share = short_car / car if car else None
    previous = previous_mission or {}
    profile: dict[str, Any] = {
        "type": "mission_profile",
        "profile_version": PROFILE_VERSION,
        "profile_status": "ready" if valid > 0 else "collecting",
        "user_id": user_id,
        "campaign_id": campaign_id,
        "source_week_start": source_week_start,
        "source_week_end": source_week_end,
        "valid_trip_count": valid,
        "invalid_trip_count": invalid,
        "invalid_trip_reasons": dict(sorted(invalid_reasons.items())),
        "car_primary_trip_count": car,
        "car_ratio": car_ratio,
        "short_car_trip_count": short_car,
        "short_car_share": short_share,
        "transit_primary_trip_count": transit,
        "low_carbon_trip_count": low_carbon,
        "carbon_change_rate": carbon_change_rate,
        "previous_mission_family": previous.get("mission_family"),
        "previous_target_count": previous.get("target_count"),
        "previous_achievement_rate": previous.get("achievement_rate"),
        "previous_mission_completed": previous.get("completed"),
    }
    canonical = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    profile["profile_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return profile


def _iso_week_label(day_iso: str) -> str:
    year, week, _ = datetime.fromisoformat(day_iso).date().isocalendar()
    return f"{year}-W{week:02d}"


def _carbon_change_map(spark, campaign_id: str, source_week_start: str):
    """Return recent weekly carbon change when both weekly Gold rows exist."""
    from pyspark.sql import functions as F

    source_day = datetime.fromisoformat(source_week_start).date()
    current_week = _iso_week_label(source_week_start)
    previous_week = _iso_week_label((source_day - timedelta(days=7)).isoformat())
    try:
        weekly = spark.read.format("delta").load(GOLD_WEEKLY_USER_PATH).filter(
            (F.col("campaign_id") == campaign_id)
            & F.col("week").isin([previous_week, current_week])
        )
    except Exception:
        return {}

    values: dict[str, dict[str, float]] = {}
    for row in weekly.select("user_id", "week", "total_kg_co2e").collect():
        values.setdefault(row["user_id"], {})[row["week"]] = row["total_kg_co2e"]

    result = {}
    for user_id, weeks in values.items():
        current = weeks.get(current_week)
        previous = weeks.get(previous_week)
        result[user_id] = (
            None
            if current is None or previous is None or float(previous) <= 0
            else (float(current) - float(previous)) / float(previous)
        )
    return result


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
        for item in container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        )
    }


def _cosmos_clients():
    if not COSMOS_ENDPOINT:
        return None, None
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    profiles = db.get_container_client(COSMOS_PROFILE_CONTAINER)
    assignments = db.get_container_client(
        os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")
    )
    return profiles, assignments


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
    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        IntegerType,
        MapType,
        StringType,
        StructField,
        StructType,
    )

    spark = SparkSession.builder.getOrCreate()
    start_utc, end_utc = _utc_week_bounds(source_week_start, source_week_end)
    ended_at = F.to_timestamp(F.col("ended_at"))
    raw = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH).filter(
        (F.col("campaign_id") == campaign_id)
        & (F.col("status") == "ready")
        & (ended_at >= F.to_timestamp(F.lit(start_utc)))
        & (ended_at < F.to_timestamp(F.lit(end_utc)))
    )
    window = Window.partitionBy("trip_id").orderBy(F.col("updated_at").desc())
    raw = raw.withColumn("_rn", F.row_number().over(window)).filter(F.col("_rn") == 1).drop("_rn")

    profile_container, assignment_container = _cosmos_clients()
    previous_by_user = (
        _load_previous_assignments(assignment_container, campaign_id, source_week_start)
        if assignment_container is not None
        else {}
    )
    carbon_change_by_user = _carbon_change_map(spark, campaign_id, source_week_start)

    trip_struct = F.struct(*[F.col(name) for name in raw.columns])
    grouped = raw.groupBy("user_id").agg(F.collect_list(trip_struct).alias("trips"))
    profiles = []
    for row in grouped.collect():
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

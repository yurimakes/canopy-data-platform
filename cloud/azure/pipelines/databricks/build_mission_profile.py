"""Build weekly mission profiles: mobility fit + preference + capability."""
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
CATEGORY_IDS = ("challenge", "habit", "easy_win", "explore")
SHORT_CAR_MAX_DISTANCE_M = 2000.0
PROFILE_VERSION = "mission-profile-v2"
PREFERENCE_PRIOR_ALPHA = 1.0
PREFERENCE_PRIOR_BETA = 1.0

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
COSMOS_PROFILE_CONTAINER = os.environ.get("CANOPY_COSMOS_MISSION_PROFILE_CONTAINER", "mission-profiles")
COSMOS_MISSION_CONTAINER = os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")


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
    return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


def _segment_mode(segment: Mapping[str, Any]) -> str | None:
    value = segment.get("model_prediction")
    if not isinstance(value, str):
        return None
    value = value.lower()
    return value if value in SUPPORTED_MODES else None


def derive_trip_primary_mode(trip: Mapping[str, Any]) -> tuple[str | None, float | None, str | None]:
    """Use the unique mode with greatest summed segment distance; do not guess ties."""
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

    if not distance_by_mode or total <= 0:
        return None, None, "non_positive_distance"
    maximum = max(distance_by_mode.values())
    winners = [mode for mode, value in distance_by_mode.items() if abs(value - maximum) < 1e-9]
    if len(winners) != 1:
        return None, total, "primary_mode_tie"
    return winners[0], total, None


def compute_category_preferences(
    offer_sets: Iterable[Mapping[str, Any]],
    category_ids: Iterable[str] = CATEGORY_IDS,
    *,
    prior_alpha: float = PREFERENCE_PRIOR_ALPHA,
    prior_beta: float = PREFERENCE_PRIOR_BETA,
) -> dict[str, dict[str, float | int]]:
    """Learn preference from choice, not from mission completion.

    A week updates preference only when the user actually selects one candidate.
    The selected category is a success and the other simultaneously offered
    categories are failures. A week with no selection adds no preference evidence.
    """
    state = {
        category: {
            "alpha": float(prior_alpha),
            "beta": float(prior_beta),
            "selected_count": 0,
            "choice_set_count": 0,
        }
        for category in category_ids
    }

    for offer in sorted(offer_sets, key=lambda item: str(item.get("week_start", ""))):
        selected_template = offer.get("selected_mission_template_id")
        candidates = offer.get("candidates") or []
        if not selected_template or not isinstance(candidates, list):
            continue
        selected = next(
            (candidate for candidate in candidates if candidate.get("mission_template_id") == selected_template),
            None,
        )
        if not selected or not selected.get("category_id"):
            continue
        selected_category = selected["category_id"]
        offered_categories = {
            candidate.get("category_id") for candidate in candidates if candidate.get("category_id") in state
        }
        for category in offered_categories:
            state[category]["choice_set_count"] += 1
            if category == selected_category:
                state[category]["alpha"] += 1.0
                state[category]["selected_count"] += 1
            else:
                state[category]["beta"] += 1.0

    for category, values in state.items():
        alpha = float(values["alpha"])
        beta = float(values["beta"])
        values["posterior_mean"] = alpha / (alpha + beta)
        values["observations"] = int(values["choice_set_count"])
    return state


def compute_family_capability(assignments: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep difficulty evidence separate from category preference evidence."""
    state: dict[str, dict[str, Any]] = {}
    ordered = sorted(assignments, key=lambda item: (str(item.get("week_start", "")), str(item.get("created_at", ""))))
    for assignment in ordered:
        family = assignment.get("mission_family")
        target = assignment.get("target_count")
        rate = assignment.get("achievement_rate")
        if not isinstance(family, str) or not isinstance(target, int) or target <= 0:
            continue
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            rate = None
        row = state.setdefault(
            family,
            {
                "assignment_count": 0,
                "completed_count": 0,
                "last_target_count": None,
                "last_achievement_rate": None,
                "max_completed_target_count": 0,
            },
        )
        row["assignment_count"] += 1
        row["last_target_count"] = target
        row["last_achievement_rate"] = None if rate is None else float(rate)
        if rate is not None and float(rate) >= 1.0:
            row["completed_count"] += 1
            row["max_completed_target_count"] = max(row["max_completed_target_count"], target)
    return state


def build_profile_from_trips(
    trips: Iterable[Mapping[str, Any]],
    *,
    user_id: str,
    campaign_id: str,
    source_week_start: str,
    source_week_end: str,
    offer_history: Iterable[Mapping[str, Any]] = (),
    assignment_history: Iterable[Mapping[str, Any]] = (),
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

    category_preferences = compute_category_preferences(offer_history)
    family_capability = compute_family_capability(assignment_history)
    preference_observations = sum(int(value["observations"]) for value in category_preferences.values())
    profile_status = "ready" if valid > 0 else ("preference_only" if preference_observations > 0 else "collecting")

    assignments = sorted(
        assignment_history,
        key=lambda item: (str(item.get("week_start", "")), str(item.get("created_at", ""))),
    )
    previous = assignments[-1] if assignments else {}
    profile: dict[str, Any] = {
        "type": "mission_profile",
        "profile_version": PROFILE_VERSION,
        "profile_status": profile_status,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "source_week_start": source_week_start,
        "source_week_end": source_week_end,
        "valid_trip_count": valid,
        "invalid_trip_count": invalid,
        "invalid_trip_reasons": dict(sorted(invalid_reasons.items())),
        "car_primary_trip_count": car,
        "car_ratio": car / valid if valid else None,
        "short_car_trip_count": short_car,
        "short_car_share": short_car / car if car else None,
        "transit_primary_trip_count": transit,
        "low_carbon_trip_count": low_carbon,
        "carbon_change_rate": carbon_change_rate,
        "category_preferences": category_preferences,
        "preference_observation_count": preference_observations,
        "family_capability": family_capability,
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
    from pyspark.sql import functions as F

    source_day = datetime.fromisoformat(source_week_start).date()
    current_week = _iso_week_label(source_week_start)
    previous_week = _iso_week_label((source_day - timedelta(days=7)).isoformat())
    try:
        weekly = spark.read.format("delta").load(GOLD_WEEKLY_USER_PATH).filter(
            (F.col("campaign_id") == campaign_id) & F.col("week").isin([previous_week, current_week])
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
            None if current is None or previous is None or float(previous) <= 0
            else (float(current) - float(previous)) / float(previous)
        )
    return result


def _cosmos_clients():
    if not COSMOS_ENDPOINT:
        return None, None
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_PROFILE_CONTAINER), db.get_container_client(COSMOS_MISSION_CONTAINER)


def _load_mission_history(container, campaign_id: str, source_week_start: str):
    if container is None:
        return [], []
    query = (
        "SELECT * FROM c WHERE c.campaign_id = @campaign_id "
        "AND c.week_start <= @source_week_start "
        "AND (c.type = 'mission_offer_set' OR c.type = 'mission_assignment')"
    )
    params = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@source_week_start", "value": source_week_start},
    ]
    items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
    offers = [item for item in items if item.get("type") == "mission_offer_set"]
    assignments = [item for item in items if item.get("type") == "mission_assignment"]
    return offers, assignments


def _group_history_by_user(items: Iterable[Mapping[str, Any]]):
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        user_id = item.get("user_id")
        if isinstance(user_id, str):
            grouped[user_id].append(item)
    return grouped


def _latest_profile_document(profile: Mapping[str, Any]) -> dict[str, Any]:
    campaign_id = str(profile["campaign_id"])
    user_id = str(profile["user_id"])
    return {
        **profile,
        "id": f"mission-profile-latest:{campaign_id}:{user_id}",
        "pk": f"{campaign_id}:{user_id}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _gold_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(profile)
    result["category_preferences_json"] = json.dumps(result.pop("category_preferences"), ensure_ascii=False, sort_keys=True)
    result["family_capability_json"] = json.dumps(result.pop("family_capability"), ensure_ascii=False, sort_keys=True)
    return result


def run(campaign_id: str, source_week_start: str, source_week_end: str):
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F
    from pyspark.sql.types import BooleanType, DoubleType, IntegerType, MapType, StringType, StructField, StructType

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

    trip_struct = F.struct(*[F.col(name) for name in raw.columns])
    trip_rows = raw.groupBy("user_id").agg(F.collect_list(trip_struct).alias("trips")).collect()
    trips_by_user = {
        row["user_id"]: [trip.asDict(recursive=True) for trip in row["trips"]]
        for row in trip_rows
    }

    profile_container, mission_container = _cosmos_clients()
    offers, assignments = _load_mission_history(mission_container, campaign_id, source_week_start)
    offers_by_user = _group_history_by_user(offers)
    assignments_by_user = _group_history_by_user(assignments)
    carbon_by_user = _carbon_change_map(spark, campaign_id, source_week_start)

    # Include users known from Trip data or mission history. A completely new user with
    # no Trip and no history is handled by API cold start and does not need a profile row.
    users = sorted(set(trips_by_user) | set(offers_by_user) | set(assignments_by_user))
    profiles = []
    for user_id in users:
        profile = build_profile_from_trips(
            trips_by_user.get(user_id, []),
            user_id=user_id,
            campaign_id=campaign_id,
            source_week_start=source_week_start,
            source_week_end=source_week_end,
            offer_history=offers_by_user.get(user_id, []),
            assignment_history=assignments_by_user.get(user_id, []),
            carbon_change_rate=carbon_by_user.get(user_id),
        )
        profiles.append(profile)
        if profile_container is not None:
            profile_container.upsert_item(_latest_profile_document(profile))

    if not profiles:
        print(f"[done] campaign_id={campaign_id} no profile population; API cold start remains available")
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
        StructField("preference_observation_count", IntegerType(), False),
        StructField("category_preferences_json", StringType(), False),
        StructField("family_capability_json", StringType(), False),
        StructField("previous_mission_family", StringType(), True),
        StructField("previous_target_count", IntegerType(), True),
        StructField("previous_achievement_rate", DoubleType(), True),
        StructField("previous_mission_completed", BooleanType(), True),
        StructField("profile_hash", StringType(), False),
    ])
    out = spark.createDataFrame([_gold_profile(profile) for profile in profiles], schema=schema)
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

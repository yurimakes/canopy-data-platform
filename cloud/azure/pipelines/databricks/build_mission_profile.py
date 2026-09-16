"""주간 미션 프로필 생성: 이동행동 + 성향 + 공통 난이도.

성향은 사용자가 완료한 비교가능 미션만 양의 증거로 누적한다.
미완료는 난이도·기회 부족·비선호를 구분하기 어려우므로 감점하지 않는다.
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
SUPPORTED_MODES = LOW_CARBON_MODES | {"car"}
CATEGORY_IDS = ("challenge", "habit", "easy_win", "explore")
SHORT_CAR_MAX_DISTANCE_M = 2000.0
PROFILE_VERSION = "mission-profile-v3"
PREFERENCE_PRIOR = 1.0

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
    """세그먼트 거리 합이 유일하게 가장 큰 mode만 Trip 대표 mode로 사용한다."""
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
    maximum = max(distance_by_mode.values()) if distance_by_mode else 0.0
    winners = [mode for mode, value in distance_by_mode.items() if abs(value - maximum) < 1e-9]
    if not winners:
        return None, None, "non_positive_distance"
    if len(winners) != 1:
        return None, total, "primary_mode_tie"
    return winners[0], total, None


def compute_category_preferences(
    bundles: Iterable[Mapping[str, Any]],
    category_ids: Iterable[str] = CATEGORY_IDS,
    *,
    prior: float = PREFERENCE_PRIOR,
) -> dict[str, dict[str, float | int]]:
    """완료된 비교가능 미션만 성향의 양의 증거로 누적한다."""
    state = {
        category: {
            "prior": float(prior),
            "assigned_count": 0,
            "comparable_assigned_count": 0,
            "completed_count": 0,
            "positive_evidence_count": 0,
        }
        for category in category_ids
    }
    for bundle in sorted(bundles, key=lambda item: str(item.get("week_start", ""))):
        for mission in bundle.get("missions") or []:
            category = mission.get("category_id")
            if category not in state:
                continue
            row = state[category]
            row["assigned_count"] += 1
            comparable = mission.get("preference_comparable") is True
            if comparable:
                row["comparable_assigned_count"] += 1
            if mission.get("completed") is True:
                row["completed_count"] += 1
                if comparable:
                    row["positive_evidence_count"] += 1
    total_mass = sum(float(row["prior"]) + int(row["positive_evidence_count"]) for row in state.values())
    for row in state.values():
        mass = float(row["prior"]) + int(row["positive_evidence_count"])
        row["preference_share"] = mass / total_mass if total_mass > 0 else 0.0
    return state


def compute_difficulty_state(bundles: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """가장 최근 주의 비교가능 미션 수행 결과를 다음 주 공통 난이도 입력으로 만든다."""
    ordered = sorted(bundles, key=lambda item: (str(item.get("week_start", "")), str(item.get("created_at", ""))))
    for bundle in reversed(ordered):
        missions = [m for m in (bundle.get("missions") or []) if m.get("preference_comparable") is True]
        target = bundle.get("common_target_count")
        if not missions or not isinstance(target, int) or target <= 0:
            continue
        completed = sum(1 for mission in missions if mission.get("completed") is True)
        return {
            "last_week_start": bundle.get("week_start"),
            "last_common_target_count": target,
            "last_comparable_mission_count": len(missions),
            "last_completed_comparable_count": completed,
        }
    return {
        "last_week_start": None,
        "last_common_target_count": None,
        "last_comparable_mission_count": 0,
        "last_completed_comparable_count": 0,
    }


def compute_family_capability(bundles: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    ordered = sorted(bundles, key=lambda item: (str(item.get("week_start", "")), str(item.get("created_at", ""))))
    for bundle in ordered:
        for mission in bundle.get("missions") or []:
            family = mission.get("mission_family")
            target = mission.get("target_count")
            rate = mission.get("achievement_rate")
            if not isinstance(family, str) or not isinstance(target, int) or target <= 0:
                continue
            row = state.setdefault(family, {
                "assignment_count": 0,
                "completed_count": 0,
                "last_target_count": None,
                "last_achievement_rate": None,
                "max_completed_target_count": 0,
            })
            row["assignment_count"] += 1
            row["last_target_count"] = target
            row["last_achievement_rate"] = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
            if mission.get("completed") is True:
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
    bundle_history: Iterable[Mapping[str, Any]] = (),
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

    bundles = list(bundle_history)
    category_preferences = compute_category_preferences(bundles)
    difficulty_state = compute_difficulty_state(bundles)
    family_capability = compute_family_capability(bundles)
    positive_evidence_count = sum(int(row["positive_evidence_count"]) for row in category_preferences.values())
    profile_status = "ready" if valid > 0 else ("history_only" if bundles else "collecting")

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
        "preference_positive_evidence_count": positive_evidence_count,
        "difficulty_state": difficulty_state,
        "family_capability": family_capability,
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
        result[user_id] = None if current is None or previous is None or float(previous) <= 0 else (float(current) - float(previous)) / float(previous)
    return result


def _cosmos_clients():
    if not COSMOS_ENDPOINT:
        return None, None
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_PROFILE_CONTAINER), db.get_container_client(COSMOS_MISSION_CONTAINER)


def _load_mission_bundles(container, campaign_id: str, source_week_start: str):
    if container is None:
        return []
    query = (
        "SELECT * FROM c WHERE c.campaign_id = @campaign_id "
        "AND c.week_start <= @source_week_start AND c.type = 'mission_bundle'"
    )
    params = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@source_week_start", "value": source_week_start},
    ]
    return list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))


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
    return {**profile, "id": f"mission-profile-latest:{campaign_id}:{user_id}", "pk": f"{campaign_id}:{user_id}", "updated_at": datetime.now(timezone.utc).isoformat()}


def _gold_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(profile)
    result["category_preferences_json"] = json.dumps(result.pop("category_preferences"), ensure_ascii=False, sort_keys=True)
    result["difficulty_state_json"] = json.dumps(result.pop("difficulty_state"), ensure_ascii=False, sort_keys=True)
    result["family_capability_json"] = json.dumps(result.pop("family_capability"), ensure_ascii=False, sort_keys=True)
    return result


def run(campaign_id: str, source_week_start: str, source_week_end: str):
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F
    from pyspark.sql.types import DoubleType, IntegerType, MapType, StringType, StructField, StructType

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
    trips_by_user = {row["user_id"]: [trip.asDict(recursive=True) for trip in row["trips"]] for row in trip_rows}

    profile_container, mission_container = _cosmos_clients()
    bundles = _load_mission_bundles(mission_container, campaign_id, source_week_start)
    bundles_by_user = _group_history_by_user(bundles)
    carbon_by_user = _carbon_change_map(spark, campaign_id, source_week_start)
    users = sorted(set(trips_by_user) | set(bundles_by_user))
    profiles = []
    for user_id in users:
        profile = build_profile_from_trips(
            trips_by_user.get(user_id, []),
            user_id=user_id,
            campaign_id=campaign_id,
            source_week_start=source_week_start,
            source_week_end=source_week_end,
            bundle_history=bundles_by_user.get(user_id, []),
            carbon_change_rate=carbon_by_user.get(user_id),
        )
        profiles.append(profile)
        if profile_container is not None:
            profile_container.upsert_item(_latest_profile_document(profile))

    if not profiles:
        print(f"[완료] campaign_id={campaign_id} 프로필 대상 없음; 신규 사용자는 API cold start 사용")
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
        StructField("preference_positive_evidence_count", IntegerType(), False),
        StructField("category_preferences_json", StringType(), False),
        StructField("difficulty_state_json", StringType(), False),
        StructField("family_capability_json", StringType(), False),
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
    print(f"[완료] campaign_id={campaign_id} profiles={len(profiles)} source_week={source_week_start}")
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

"""Materialize canonical weekly Mission Profile Gold and Cosmos latest rows.

The Mission Profile policy stays in ``build_mission_profile.py``. This module
only adapts the managed Weekly Gold table and Mission Response Gold history to
that core, writes one deterministic campaign/week partition, and then updates
the latest serving projection in Cosmos.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_PROFILE_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/"
    "gold/mission_profile/"
)
DEFAULT_RESPONSE_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/"
    "gold/mission_response_weekly/"
)
DEFAULT_DATABASE = "canopy-db"
SERVICE_CREDENTIAL_ENV = "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME"
PROFILE_CONTAINER_ENV = "CANOPY_COSMOS_MISSION_PROFILE_CONTAINER"


def _databricks_module_dir() -> Path:
    starts = []
    if "__file__" in globals():
        starts.append(Path(__file__).resolve().parent)
    starts.append(Path.cwd().resolve())

    for start in starts:
        for path in (start, *start.parents):
            if (path / "build_mission_profile.py").exists():
                return path
            candidate = (
                path
                / "cloud"
                / "azure"
                / "pipelines"
                / "databricks"
            )
            if (candidate / "build_mission_profile.py").exists():
                return candidate
    raise RuntimeError("Databricks Mission module directory not found")


def _iso_week_bounds(week: str) -> tuple[str, str]:
    week = (week or "").strip()
    if not week or "{{" in week:
        raise ValueError("Resolved ISO week required")
    try:
        monday = datetime.strptime(f"{week}-1", "%G-W%V-%u").date()
    except ValueError as exc:
        raise ValueError("week must use ISO YYYY-Www format") from exc
    if monday.strftime("%G-W%V") != week:
        raise ValueError("week must use a valid ISO YYYY-Www value")
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()


def _service_credential_name(configured_name: str | None = None) -> str:
    name = (
        (configured_name or "").strip()
        or os.environ.get(SERVICE_CREDENTIAL_ENV, "").strip()
    )
    if not name:
        raise RuntimeError(
            f"{SERVICE_CREDENTIAL_ENV} is required for Databricks Mission Profile runs"
        )
    if "{{" in name:
        raise RuntimeError("Resolved Databricks service credential name required")
    return name


def _profile_container_name(configured_name: str | None = None) -> str:
    name = (
        (configured_name or "").strip()
        or os.environ.get(PROFILE_CONTAINER_ENV, "").strip()
    )
    if not name:
        raise RuntimeError(
            "Mission Profile container required via --profile-container or "
            f"{PROFILE_CONTAINER_ENV}"
        )
    if "{{" in name:
        raise RuntimeError("Resolved Mission Profile container name required")
    return name


def _cosmos_endpoint(configured_endpoint: str | None = None) -> str:
    endpoint = (
        (configured_endpoint or "").strip()
        or os.environ.get("CANOPY_COSMOS_ENDPOINT", "").strip()
    )
    if not endpoint:
        raise RuntimeError("Cosmos endpoint required via --endpoint or CANOPY_COSMOS_ENDPOINT")
    if "{{" in endpoint:
        raise RuntimeError("Resolved Cosmos endpoint required")
    return endpoint


def _profile_container(
    *,
    service_credential_name: str,
    profile_container_name: str,
    endpoint: str,
):
    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils

    credential = dbutils.credentials.getServiceCredentialsProvider(
        service_credential_name
    )
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(
        os.environ.get("CANOPY_COSMOS_DATABASE", DEFAULT_DATABASE)
    )
    return database.get_container_client(profile_container_name)


def _read_weekly_source(spark, source: str):
    source = (source or "").strip()
    if not source or "{{" in source:
        raise ValueError("Resolved --weekly-source required")
    if source.startswith("table:"):
        table_name = source.removeprefix("table:").strip()
        if not table_name:
            raise ValueError("weekly table name required after table:")
        return spark.table(table_name)
    return spark.read.format("delta").load(source)


def _weekly_summary_maps(
    spark,
    source: str,
    campaign_id: str,
    source_week_start: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, float | None]]:
    from pyspark.sql import functions as F

    source_day = datetime.fromisoformat(source_week_start).date()
    current_week = source_day.strftime("%G-W%V")
    previous_week = (source_day - timedelta(days=7)).strftime("%G-W%V")
    weekly = _read_weekly_source(spark, source)

    required = {
        "campaign_id", "user_id", "week", "trip_count", "total_kg_co2e",
        "valid_primary_trip_count", "invalid_primary_trip_count",
        "ambiguous_primary_trip_count", "invalid_segment_primary_trip_count",
        "car_primary_trip_count", "short_car_trip_count",
        "transit_primary_trip_count", "low_carbon_trip_count",
    }
    missing = sorted(required - set(weekly.columns))
    if missing:
        raise ValueError(
            "Weekly Gold is missing Mission Profile columns: "
            + ", ".join(missing)
        )

    rows = (
        weekly.where(
            (F.col("campaign_id") == campaign_id)
            & F.col("week").isin(previous_week, current_week)
        )
        .collect()
    )
    current: dict[str, dict[str, Any]] = {}
    carbon: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in rows:
        item = row.asDict(recursive=True)
        user_id = str(item["user_id"])
        week = str(item["week"])
        carbon[user_id][week] = item.get("total_kg_co2e")
        if week == current_week:
            if user_id in current:
                raise RuntimeError(
                    "Weekly Gold has duplicate campaign/user/week rows"
                )
            current[user_id] = item

    change: dict[str, float | None] = {}
    for user_id, weeks in carbon.items():
        now = weeks.get(current_week)
        previous = weeks.get(previous_week)
        change[user_id] = (
            None
            if now is None or previous is None or float(previous) <= 0
            else (float(now) - float(previous)) / float(previous)
        )
    return current, change


def _response_history_by_user(
    spark,
    campaign_id: str,
    source_week_start: str,
    *,
    response_path: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    from pyspark.sql import functions as F

    target = response_path or os.environ.get(
        "CANOPY_GOLD_MISSION_RESPONSE_PATH",
        DEFAULT_RESPONSE_PATH,
    )
    try:
        response = spark.read.format("delta").load(target)
        _ = response.columns
    except Exception as exc:
        if "PATH_NOT_FOUND" not in str(exc):
            raise
        return {}

    required = {
        "campaign_id", "user_id", "week_start", "week_end", "bundle_id",
        "common_target_count", "category_id", "mission_family",
        "target_count", "achievement_rate", "completed",
        "affinity_comparable", "difficulty_comparable",
    }
    missing = sorted(required - set(response.columns))
    if missing:
        raise ValueError(
            "Mission Response Gold is missing profile history columns: "
            + ", ".join(missing)
        )

    rows = (
        response.where(
            (F.col("campaign_id") == campaign_id)
            & (F.col("week_start") <= source_week_start)
        )
        .collect()
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = row.asDict(recursive=True)
        user_id = item.get("user_id")
        if isinstance(user_id, str) and user_id:
            grouped[user_id].append(item)
    return dict(grouped)


def _profile_schema():
    from pyspark.sql.types import (
        DoubleType,
        IntegerType,
        MapType,
        StringType,
        StructField,
        StructType,
    )

    return StructType([
        StructField("type", StringType(), False),
        StructField("profile_version", StringType(), False),
        StructField("profile_status", StringType(), False),
        StructField("user_id", StringType(), False),
        StructField("campaign_id", StringType(), False),
        StructField("source_week_start", StringType(), False),
        StructField("source_week_end", StringType(), False),
        StructField("effective_week_start", StringType(), False),
        StructField("valid_trip_count", IntegerType(), False),
        StructField("invalid_trip_count", IntegerType(), False),
        StructField(
            "invalid_trip_reasons",
            MapType(StringType(), IntegerType()),
            False,
        ),
        StructField("car_primary_trip_count", IntegerType(), False),
        StructField("car_ratio", DoubleType(), True),
        StructField("short_car_trip_count", IntegerType(), False),
        StructField("short_car_share", DoubleType(), True),
        StructField("transit_primary_trip_count", IntegerType(), False),
        StructField("low_carbon_trip_count", IntegerType(), False),
        StructField("carbon_change_rate", DoubleType(), True),
        StructField("mission_history_source", StringType(), False),
        StructField("preference_positive_evidence_count", IntegerType(), False),
        StructField("category_preferences_json", StringType(), False),
        StructField("difficulty_state_json", StringType(), False),
        StructField("family_capability_json", StringType(), False),
        StructField("profile_hash", StringType(), False),
    ])


def _write_profile_partition(
    spark,
    rows: list[dict[str, Any]],
    campaign_id: str,
    source_week_start: str,
) -> str:
    from pyspark.sql import functions as F

    target = os.environ.get(
        "CANOPY_GOLD_MISSION_PROFILE_PATH",
        DEFAULT_PROFILE_PATH,
    )
    frame = spark.createDataFrame(rows, schema=_profile_schema())
    escaped_campaign = campaign_id.replace("'", "''")
    escaped_week = source_week_start.replace("'", "''")

    if frame.where(
        (F.col("campaign_id") != campaign_id)
        | (F.col("source_week_start") != source_week_start)
    ).limit(1).count():
        raise RuntimeError(
            "Mission Profile output escaped the requested campaign/week partition"
        )

    (
        frame.write.format("delta")
        .mode("overwrite")
        .option(
            "replaceWhere",
            f"campaign_id = '{escaped_campaign}' "
            f"AND source_week_start = '{escaped_week}'",
        )
        .partitionBy("campaign_id", "source_week_start")
        .save(target)
    )
    return target


def _upsert_latest_profiles(container, profiles: Iterable[Mapping[str, Any]]) -> int:
    from build_mission_profile import _latest_profile_document

    count = 0
    for profile in profiles:
        container.upsert_item(_latest_profile_document(profile))
        count += 1
    return count


def run(
    campaign_id: str,
    source_week_start: str,
    source_week_end: str,
    *,
    weekly_source: str,
    service_credential_name: str | None = None,
    profile_container: str | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    from pyspark.sql import SparkSession

    campaign_id = (campaign_id or "").strip()
    if not campaign_id or "{{" in campaign_id:
        raise ValueError("Resolved campaign_id required")

    module_dir = _databricks_module_dir()
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    from build_mission_profile import (
        _gold_profile,
        _responses_to_bundles,
        build_profile_from_weekly_summary,
    )

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    weekly_by_user, carbon_by_user = _weekly_summary_maps(
        spark,
        weekly_source,
        campaign_id,
        source_week_start,
    )
    response_rows_by_user = _response_history_by_user(
        spark,
        campaign_id,
        source_week_start,
    )
    response_history_by_user = {
        user_id: _responses_to_bundles(rows)
        for user_id, rows in response_rows_by_user.items()
    }

    users = sorted(set(weekly_by_user) | set(response_history_by_user))
    profiles = []
    for user_id in users:
        history = response_history_by_user.get(user_id, [])
        profiles.append(build_profile_from_weekly_summary(
            weekly_by_user.get(user_id),
            user_id=user_id,
            campaign_id=campaign_id,
            source_week_start=source_week_start,
            source_week_end=source_week_end,
            bundle_history=history,
            carbon_change_rate=carbon_by_user.get(user_id),
            mission_history_source=(
                "mission_response_gold" if history else "none"
            ),
        ))

    if not profiles:
        result = {
            "status": "NO_PROFILE_ROWS",
            "campaign_id": campaign_id,
            "source_week_start": source_week_start,
            "source_week_end": source_week_end,
            "profile_count": 0,
            "partition_write_performed": False,
            "existing_partition_preserved": True,
            "cosmos_upsert_count": 0,
        }
        print(json.dumps(result, ensure_ascii=False))
        return result

    credential_name = _service_credential_name(service_credential_name)
    container_name = _profile_container_name(profile_container)
    cosmos_endpoint = _cosmos_endpoint(endpoint)

    target = _write_profile_partition(
        spark,
        [_gold_profile(profile) for profile in profiles],
        campaign_id,
        source_week_start,
    )
    container = _profile_container(
        service_credential_name=credential_name,
        profile_container_name=container_name,
        endpoint=cosmos_endpoint,
    )
    upsert_count = _upsert_latest_profiles(container, profiles)

    result = {
        "status": "MISSION_PROFILE_WEEKLY_MATERIALIZATION_PASSED",
        "campaign_id": campaign_id,
        "source_week_start": source_week_start,
        "source_week_end": source_week_end,
        "profile_count": len(profiles),
        "partition_write_performed": True,
        "cosmos_upsert_count": upsert_count,
        "target": target,
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def parse_args(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--weekly-source", required=True)
    parser.add_argument("--service-credential-name")
    parser.add_argument("--profile-container")
    parser.add_argument("--endpoint")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    source_week_start, source_week_end = _iso_week_bounds(args.week)
    return run(
        args.campaign_id,
        source_week_start,
        source_week_end,
        weekly_source=args.weekly_source,
        service_credential_name=args.service_credential_name,
        profile_container=args.profile_container,
        endpoint=args.endpoint,
    )


if __name__ == "__main__":
    main()

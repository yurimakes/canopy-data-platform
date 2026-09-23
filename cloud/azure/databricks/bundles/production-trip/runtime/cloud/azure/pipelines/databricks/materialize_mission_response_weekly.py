"""Mission v3.2 weekly Progress -> Response Gold materializer.

This task is intentionally outside Lakeflow transforms because issued Mission
Bundle state is operational Cosmos data. It:
1) reads frozen issued Mission Bundles from the configured Cosmos container,
2) reads canonical/dev Final Trip rows,
3) recomputes Mission Progress from the frozen completion_rule snapshot,
4) builds one Mission Response row per issued assignment,
5) deterministically rewrites only the requested campaign/week partition in
   ADLS Gold mission_response_weekly.

It does not issue new Mission Bundles, reinterpret the current policy, or use
Behavior Change as a Mission input.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_FINAL_TRIP_TABLE = "dbw_canopy_dev.sandbox.final_trips"
DEFAULT_RESPONSE_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/"
    "gold/mission_response_weekly/"
)
DEFAULT_DATABASE = "canopy-db"
DEFAULT_TIMEZONE = "Asia/Seoul"
SERVICE_CREDENTIAL_ENV = "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME"


def _databricks_module_dir() -> Path:
    starts = []
    if "__file__" in globals():
        starts.append(Path(__file__).resolve().parent)
    starts.append(Path.cwd().resolve())

    for start in starts:
        for path in (start, *start.parents):
            if (path / "mission_progress.py").exists():
                return path
            if (
                path
                / "cloud"
                / "azure"
                / "pipelines"
                / "databricks"
                / "mission_progress.py"
            ).exists():
                return path / "cloud" / "azure" / "pipelines" / "databricks"

    raise RuntimeError(
        "Databricks Mission module directory not found"
    )


def _existing_cosmos_endpoint(
    module_dir: Path,
    endpoint: str | None = None,
) -> str:
    if endpoint and endpoint.strip():
        return endpoint.strip()
    configured = os.environ.get("CANOPY_COSMOS_ENDPOINT")
    if configured:
        return configured

    config_path = module_dir.parent / "weekly_analysis" / "sync_campaign_membership.job.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    parameters = config["tasks"][0]["spark_python_task"]["parameters"]

    try:
        index = parameters.index("--endpoint")
    except ValueError as exc:
        raise RuntimeError(
            "Existing team Cosmos endpoint was not found in sync_campaign_membership.job.json"
        ) from exc

    return str(parameters[index + 1])


def _service_credential_name(configured_name: str | None = None) -> str:
    credential_name = (
        configured_name or os.environ.get(SERVICE_CREDENTIAL_ENV) or ""
    ).strip()
    if not credential_name:
        raise RuntimeError(
            f"{SERVICE_CREDENTIAL_ENV} is required for Databricks Mission runs"
        )
    if "{{" in credential_name:
        raise RuntimeError("Resolved Databricks service credential name required")
    return credential_name


def _mission_container_name(configured_name: str | None = None) -> str:
    container_name = (
        (configured_name or "").strip()
        or (
            os.environ.get(
                "CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER",
                "",
            ).strip()
        )
    )
    if not container_name:
        raise RuntimeError(
            "Mission container required via --mission-container or "
            "CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER"
        )
    if "{{" in container_name:
        raise RuntimeError("Resolved Mission container name required")
    return container_name


def _mission_container(
    module_dir: Path,
    *,
    service_credential_name: str | None = None,
    endpoint: str | None = None,
    mission_container: str | None = None,
):
    credential_name = _service_credential_name(service_credential_name)
    container_name = _mission_container_name(mission_container)

    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils

    credential = dbutils.credentials.getServiceCredentialsProvider(
        credential_name
    )
    client = CosmosClient(
        _existing_cosmos_endpoint(module_dir, endpoint),
        credential=credential,
    )
    database = client.get_database_client(
        os.environ.get("CANOPY_COSMOS_DATABASE", DEFAULT_DATABASE)
    )
    return database.get_container_client(container_name)


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


def _read_issued_bundles(container, campaign_id: str, week_start: str):
    query = (
        "SELECT * FROM c "
        "WHERE c.campaign_id = @campaign_id "
        "AND c.week_start = @week_start "
        "AND c.type = 'mission_bundle'"
    )
    parameters = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@week_start", "value": week_start},
    ]

    bundles = list(
        container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
    )

    return bundles


def _read_trip_rows(spark, campaign_id: str, user_ids: list[str]):
    from pyspark.sql import functions as F

    table = os.environ.get(
        "CANOPY_FINAL_TRIP_TABLE",
        DEFAULT_FINAL_TRIP_TABLE,
    )
    frame = spark.read.table(table).where(
        F.col("campaign_id") == campaign_id
    )

    if user_ids:
        frame = frame.where(F.col("user_id").isin(user_ids))

    return [
        row.asDict(recursive=True)
        for row in frame.collect()
    ]


def _response_schema():
    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
    )

    return StructType([
        StructField("campaign_id", StringType(), False),
        StructField("user_id", StringType(), False),
        StructField("week_start", StringType(), False),
        StructField("week_end", StringType(), False),
        StructField("bundle_id", StringType(), False),
        StructField("assignment_id", StringType(), False),
        StructField("mission_template_id", StringType(), False),
        StructField("mission_family", StringType(), False),
        StructField("category_id", StringType(), False),
        StructField("difficulty_band", StringType(), False),
        StructField("common_target_count", LongType(), False),
        StructField("target_count", LongType(), False),
        StructField("affinity_comparable", BooleanType(), False),
        StructField("difficulty_comparable", BooleanType(), False),
        StructField("preference_comparable", BooleanType(), False),
        StructField("mission_shown_count", LongType(), False),
        StructField("mission_started_count", LongType(), False),
        StructField("mission_completed_count", LongType(), False),
        StructField("progress_count", LongType(), False),
        StructField("achievement_rate", DoubleType(), False),
        StructField("completed", BooleanType(), False),
        StructField("linked_trip_count", LongType(), False),
        StructField("policy_version", StringType(), False),
        StructField("response_version", StringType(), False),
    ])


def _write_response_partition(
    spark,
    rows: list[dict[str, Any]],
    campaign_id: str,
    week_start: str,
) -> str:
    from pyspark.sql import functions as F

    target = os.environ.get(
        "CANOPY_GOLD_MISSION_RESPONSE_PATH",
        DEFAULT_RESPONSE_PATH,
    )
    frame = spark.createDataFrame(rows, schema=_response_schema())

    if frame.where(
        (F.col("campaign_id") != campaign_id)
        | (F.col("week_start") != week_start)
    ).limit(1).count():
        raise RuntimeError(
            "Mission Response output escaped the requested campaign/week partition"
        )

    (
        frame.write.format("delta")
        .mode("overwrite")
        .option(
            "replaceWhere",
            "campaign_id = '" + campaign_id.replace("'", "''")
            + "' AND week_start = '" + week_start.replace("'", "''") + "'",
        )
        .partitionBy("campaign_id", "week_start")
        .save(target)
    )

    return target


def _verify_response_partition(
    spark,
    target: str,
    campaign_id: str,
    week_start: str,
    expected_assignments: int,
) -> dict[str, Any]:
    from pyspark.sql import functions as F

    frame = (
        spark.read.format("delta")
        .load(target)
        .where(
            (F.col("campaign_id") == campaign_id)
            & (F.col("week_start") == week_start)
        )
    )

    row_count = frame.count()
    distinct_assignment_count = frame.select(
        "assignment_id"
    ).distinct().count()
    completed_count = frame.where(
        F.col("completed") == F.lit(True)
    ).count()
    progress_sum = frame.agg(
        F.sum("progress_count").alias("progress_sum")
    ).first()["progress_sum"]

    if row_count != expected_assignments:
        raise RuntimeError(
            f"Mission Response row_count={row_count}; "
            f"expected={expected_assignments}"
        )
    if distinct_assignment_count != expected_assignments:
        raise RuntimeError(
            "Mission Response assignment_id uniqueness check failed"
        )

    return {
        "row_count": int(row_count),
        "distinct_assignment_count": int(distinct_assignment_count),
        "completed_count": int(completed_count),
        "progress_sum": int(progress_sum or 0),
    }


def run(
    campaign_id: str,
    week_start: str,
    week_end: str,
    *,
    service_credential_name: str | None = None,
    endpoint: str | None = None,
    mission_container: str | None = None,
) -> dict[str, Any]:
    from pyspark.sql import SparkSession

    campaign_id = (campaign_id or "").strip()
    if not campaign_id or "{{" in campaign_id:
        raise ValueError("Resolved campaign_id required")

    module_dir = _databricks_module_dir()
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from mission_progress import build_progress_rows
    from build_mission_response import build_response_rows

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    bundles = _read_issued_bundles(
        _mission_container(
            module_dir,
            service_credential_name=service_credential_name,
            endpoint=endpoint,
            mission_container=mission_container,
        ),
        campaign_id,
        week_start,
    )

    if not bundles:
        result = {
            "status": "NO_ISSUED_BUNDLE",
            "campaign_id": campaign_id,
            "week_start": week_start,
            "week_end": week_end,
            "bundle_count": 0,
            "issued_assignment_count": 0,
            "final_trip_rows_read": 0,
            "progress_rows": 0,
            "partition_write_performed": False,
            "existing_partition_preserved": True,
            "mission_bundle_issued_here": False,
            "current_policy_reinterpreted": False,
            "behavior_change_used": False,
        }
        print(json.dumps(result, ensure_ascii=False, default=str))
        return result

    mismatched = [
        bundle.get("bundle_id")
        for bundle in bundles
        if bundle.get("week_end") != week_end
    ]
    if mismatched:
        raise RuntimeError(
            "Issued Mission Bundle week_end differs from requested week_end: "
            + ", ".join(str(value) for value in mismatched)
        )

    user_ids = sorted({
        str(bundle["user_id"])
        for bundle in bundles
        if bundle.get("user_id")
    })
    trip_rows = _read_trip_rows(
        spark,
        campaign_id,
        user_ids,
    )

    as_of_iso = datetime.now(timezone.utc).isoformat()
    progress_rows = build_progress_rows(
        bundles,
        trip_rows,
        campaign_timezone=os.environ.get(
            "CANOPY_CAMPAIGN_TIMEZONE",
            DEFAULT_TIMEZONE,
        ),
        as_of_iso=as_of_iso,
    )
    response_rows = build_response_rows(
        bundles,
        progress_rows,
    )

    expected_assignments = sum(
        len(bundle.get("missions") or [])
        for bundle in bundles
    )
    if len(response_rows) != expected_assignments:
        raise RuntimeError(
            "Mission Response builder did not preserve every issued assignment"
        )

    target = _write_response_partition(
        spark,
        response_rows,
        campaign_id,
        week_start,
    )
    verification = _verify_response_partition(
        spark,
        target,
        campaign_id,
        week_start,
        expected_assignments,
    )

    result = {
        "status": "MISSION_RESPONSE_WEEKLY_MATERIALIZATION_PASSED",
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "bundle_count": len(bundles),
        "issued_assignment_count": expected_assignments,
        "final_trip_rows_read": len(trip_rows),
        "progress_rows": len(progress_rows),
        "response": verification,
        "mission_bundle_issued_here": False,
        "current_policy_reinterpreted": False,
        "behavior_change_used": False,
        "target": target,
    }
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


def parse_args(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--service-credential-name")
    parser.add_argument("--endpoint")
    parser.add_argument("--mission-container")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    week_start, week_end = _iso_week_bounds(args.week)
    return run(
        args.campaign_id,
        week_start,
        week_end,
        service_credential_name=args.service_credential_name,
        endpoint=args.endpoint,
        mission_container=args.mission_container,
    )


if __name__ == "__main__":
    main()

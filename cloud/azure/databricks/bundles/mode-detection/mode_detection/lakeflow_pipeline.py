"""Lakeflow pipeline for stateful mode detection."""

from __future__ import annotations

import json

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from mode_detection.spark_contracts import COMPLETE_PAYLOAD_SCHEMA_DDL
from mode_detection.spark_events import unified_events
from mode_detection.spark_processor import stateful_mode_detection_rows
from mode_detection.cosmos_sink import open_container, project_payload


def _spark() -> SparkSession:
    session = SparkSession.getActiveSession()
    if session is None:
        raise RuntimeError("Lakeflow pipeline requires an active SparkSession")
    return session


def _conf(name: str) -> str:
    value = _spark().conf.get(f"canopy.{name}")
    if not value or not value.strip():
        raise ValueError(f"missing configuration canopy.{name}")
    return value.strip()


def _bool_conf(name: str) -> bool:
    raw = _conf(name).lower()
    if raw not in ("true", "false"):
        raise ValueError(f"invalid canopy.{name}: {raw!r}")
    return raw == "true"


def _positive_int_conf(name: str) -> int:
    raw = _conf(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid canopy.{name}: {raw!r}") from exc
    if value < 1:
        raise ValueError(f"invalid canopy.{name}: {raw!r}")
    return value


CATALOG = _conf("catalog")
SILVER_SCHEMA = _conf("silver_schema")
OUTPUT_SCHEMA = _conf("output_schema")
GPS_TABLE = f"{CATALOG}.{SILVER_SCHEMA}.{_conf('gps_observations_table')}"
TRIP_END_TABLE = f"{CATALOG}.{SILVER_SCHEMA}.{_conf('trip_ended_events_table')}"
OUTPUT_TABLE = f"{CATALOG}.{OUTPUT_SCHEMA}.{_conf('complete_payloads_table')}"
MODEL_ARTIFACT_PATH = _conf("model_artifact_path")
TRANSIT_REFERENCE_ROOT = _conf("transit_reference_root")
TRANSIT_REFERENCE_DIR = _conf("transit_reference_dir")
CARBON_POLICY_PATH = _conf("carbon_policy_path")
PREDICTION_STRIDE_SECONDS = _positive_int_conf("prediction_stride_seconds")
GPS_GAP_TOLERANCE_SECONDS = _positive_int_conf("gps_gap_tolerance_seconds")
STATE_TTL_MS = _positive_int_conf("state_ttl_ms")
STATE_STORE_PARTITIONS = _positive_int_conf("state_store_partitions")
DIRECT_COSMOS_SINK_ENABLED = _bool_conf("direct_cosmos_sink_enabled")
COSMOS_ENDPOINT = _conf("cosmos_endpoint")
COSMOS_DATABASE = _conf("cosmos_database")
COSMOS_CONTAINER = _conf("cosmos_container")
ALLOW_MISSING_COSMOS_CREATE = _bool_conf("allow_missing_cosmos_create")


@dp.table(
    name=OUTPUT_TABLE,
    schema=COMPLETE_PAYLOAD_SCHEMA_DDL,
    comment="Final complete trip payload emitted directly by the stateful mode-detection runtime.",
    spark_conf={
        "spark.sql.streaming.stateStore.partitions": str(STATE_STORE_PARTITIONS)
    },
)
def complete_payloads():
    observations = _spark().readStream.table(GPS_TABLE)
    trip_ends = _spark().readStream.table(TRIP_END_TABLE)
    events = unified_events(observations, trip_ends)
    return stateful_mode_detection_rows(
        events,
        ttl_duration_ms=STATE_TTL_MS,
        artifact_path=MODEL_ARTIFACT_PATH,
        prediction_stride_seconds=PREDICTION_STRIDE_SECONDS,
        gps_gap_tolerance_seconds=GPS_GAP_TOLERANCE_SECONDS,
        reference_root=TRANSIT_REFERENCE_ROOT,
        transit_reference_dir=TRANSIT_REFERENCE_DIR,
        carbon_policy_path=CARBON_POLICY_PATH,
    )


if DIRECT_COSMOS_SINK_ENABLED:
    @dp.foreach_batch_sink(name="complete_payloads_to_cosmos")
    def complete_payloads_to_cosmos(batch_df, batch_id):
        del batch_id

        # ForEachBatch runs in a cloned streaming worker where dbutils/dbruntime
        # is not guaranteed to exist. Read the Databricks secret-backed Spark
        # configuration through the batch DataFrame's SparkSession instead.
        credential = batch_df.sparkSession.conf.get("spark.canopy.cosmos_credential")
        if (
            not credential
            or credential == "[REDACTED]"
            or credential.startswith("{{secrets/")
        ):
            raise RuntimeError(
                "Cosmos credential secret reference was not resolved in the "
                "ForEachBatch Spark configuration"
            )

        container = open_container(
            COSMOS_ENDPOINT,
            COSMOS_DATABASE,
            COSMOS_CONTAINER,
            credential,
        )

        for row in batch_df.select("document_json").toLocalIterator():
            payload = json.loads(row["document_json"])
            project_payload(
                container,
                payload,
                allow_missing_create=ALLOW_MISSING_COSMOS_CREATE,
            )


    @dp.append_flow(
        target="complete_payloads_to_cosmos",
        name="complete_payloads_to_cosmos_flow",
    )
    def complete_payloads_to_cosmos_flow():
        return _spark().readStream.table(OUTPUT_TABLE)

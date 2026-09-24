"""Lakeflow pipeline for stateful mode detection."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from mode_detection.spark_contracts import COMPLETE_PAYLOAD_SCHEMA_DDL
from mode_detection.spark_events import unified_events
from mode_detection.spark_processor import stateful_mode_detection_rows


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
STATE_TTL_MS = _positive_int_conf("state_ttl_ms")
STATE_STORE_PARTITIONS = _positive_int_conf("state_store_partitions")


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
        reference_root=TRANSIT_REFERENCE_ROOT,
        transit_reference_dir=TRANSIT_REFERENCE_DIR,
        carbon_policy_path=CARBON_POLICY_PATH,
    )

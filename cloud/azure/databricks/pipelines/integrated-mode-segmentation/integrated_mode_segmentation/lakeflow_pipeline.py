"""Integrated replay pipeline: point inference plus incremental segmentation."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from mode_inference.configuration import state_timeout_ms
from mode_inference.contracts import (
    ENRICHED_MODE_PREDICTIONS_SCHEMA_DDL,
    MODE_PREDICTIONS_SCHEMA_DDL,
)
from mode_inference.model_inference import infer_enriched_predictions, public_predictions
from mode_inference.state import stateful_feature_rows

from integrated_mode_segmentation.contracts import SEGMENT_OUTPUT_SCHEMA_DDL
from integrated_mode_segmentation.events import unified_events
from integrated_mode_segmentation.processor import stateful_segment_rows


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
SCHEMA = _conf("schema")
GPS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('input_observations_table')}"
TRIP_END_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('input_trip_ended_table')}"
OUTPUT_PREDICTIONS_TABLE = _conf("output_predictions_table")
OUTPUT_ENRICHED_PREDICTIONS_TABLE = _conf("output_enriched_predictions_table")
OUTPUT_SEGMENTS_TABLE = _conf("output_segments_table")
OUTPUT_PREDICTIONS_FQN = f"{CATALOG}.{SCHEMA}.{OUTPUT_PREDICTIONS_TABLE}"
OUTPUT_SEGMENTS_FQN = f"{CATALOG}.{SCHEMA}.{OUTPUT_SEGMENTS_TABLE}"
MODEL_URI = _conf("transition_model_uri")
MODEL_ARTIFACT_PATH = _conf("transition_model_artifact_path")
STATE_TIMEOUT_MS = state_timeout_ms(_conf("state_timeout"))
MAX_REPAIR_GAP_SECONDS = _positive_int_conf("max_repair_gap_seconds")
STATE_STORE_PARTITIONS = _positive_int_conf("state_store_partitions")


@dp.temporary_view(
    name=OUTPUT_ENRICHED_PREDICTIONS_TABLE,
    comment="Internal enriched point predictions shared by public output and segmentation.",
)
def enriched_mode_predictions():
    observations = _spark().readStream.table(GPS_TABLE)
    features = stateful_feature_rows(observations, STATE_TIMEOUT_MS)
    return infer_enriched_predictions(
        features,
        _spark(),
        MODEL_URI,
        MODEL_ARTIFACT_PATH,
    )


@dp.table(
    name=OUTPUT_PREDICTIONS_FQN,
    schema=MODE_PREDICTIONS_SCHEMA_DDL,
    comment="Integrated replay pointwise predictions; public compatibility contract.",
    spark_conf={"spark.sql.streaming.stateStore.partitions": str(STATE_STORE_PARTITIONS)},
)
def mode_predictions():
    enriched = _spark().readStream.table(OUTPUT_ENRICHED_PREDICTIONS_TABLE)
    return public_predictions(enriched)


@dp.table(
    name=OUTPUT_SEGMENTS_FQN,
    schema=SEGMENT_OUTPUT_SCHEMA_DDL,
    comment="Finalized mode segments from incremental native per-trip state.",
    spark_conf={"spark.sql.streaming.stateStore.partitions": str(STATE_STORE_PARTITIONS)},
)
def mode_segments():
    predictions = _spark().readStream.table(OUTPUT_ENRICHED_PREDICTIONS_TABLE)
    trip_ends = _spark().readStream.table(TRIP_END_TABLE)
    events = unified_events(predictions, trip_ends)
    return stateful_segment_rows(
        events,
        STATE_TIMEOUT_MS,
        MAX_REPAIR_GAP_SECONDS,
    )

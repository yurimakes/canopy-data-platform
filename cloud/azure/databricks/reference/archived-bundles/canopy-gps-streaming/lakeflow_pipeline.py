"""Serverless Lakeflow pipeline definition for Canopy GPS streaming.

Lakeflow owns query lifecycle and checkpoints. The framework-neutral GPS core,
row-based transformWithState processor, and bounded SpeedTransformer inference
logic remain in their existing modules.
"""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

# Lakeflow automatically adds the pipeline root folder to ``sys.path``. The
# bundle sync root contains the ``gps_streaming`` package directly, so no
# ``__file__``-based path manipulation is required (and ``__file__`` is not
# defined when Lakeflow evaluates Python source files).
from gps_streaming.databricks_adapter import (
    DatabricksInferenceConfig,
    build_foreach_batch_handler,
    ensure_prediction_table,
)
from gps_streaming.deployment_config import CanopyTableConfig
from gps_streaming.event_hubs_auth import connection_string, jaas_config
from gps_streaming.spark_ingestion import (
    bronze_rows,
    parse_bronze_rows,
    quarantine_rows,
    valid_observation_rows,
)
from gps_streaming.transform_with_state import (
    FEATURE_COLUMNS,
    SEGMENT_COLUMNS,
    stateful_rows,
)


def _spark() -> SparkSession:
    session = SparkSession.getActiveSession()
    if session is None:
        raise RuntimeError("Lakeflow pipeline requires an active SparkSession")
    return session


def _conf(name: str) -> str:
    value = _spark().conf.get(f"canopy.{name}")
    if not value or not value.strip():
        raise ValueError(f"missing Lakeflow pipeline configuration: canopy.{name}")
    return value.strip()


TABLES = CanopyTableConfig(
    catalog=_conf("catalog"),
    bronze_schema=_conf("bronze_schema"),
    silver_schema=_conf("silver_schema"),
    gold_schema=_conf("gold_schema"),
    ml_schema=_conf("ml_schema"),
    bronze_events_name=_conf("bronze_events_table"),
    observations_name=_conf("observations_table"),
    quarantine_name=_conf("quarantine_table"),
    features_name=_conf("features_table"),
    segments_name=_conf("segments_table"),
    predictions_name=_conf("predictions_table"),
)

# The stateful processor should execute exactly once per observation stream.
# Persist its tagged union as a private Lakeflow table, then fan out the feature
# and segment projections as ordinary managed streaming tables. This keeps
# mode_segments inside the Lakeflow dependency graph instead of treating it as
# an external foreach-batch side effect.
_STATEFUL_OUTPUT_TABLE = "canopy_gps_stateful_output"

# The checkpoint_location field belongs to the classic Structured Streaming
# compatibility adapter. Lakeflow owns the actual checkpoint for this sink.
_INFERENCE_CONFIG = DatabricksInferenceConfig(
    model_uri=_conf("model_uri"),
    checkpoint_location="lakeflow-managed",
    tables=TABLES,
)
_INFERENCE_HANDLER = None


def _event_hubs_stream():
    """Build the Event Hubs Kafka source without putting credentials in config."""
    try:
        from databricks.sdk.runtime import dbutils
    except ImportError as exc:  # pragma: no cover - Databricks runtime boundary
        raise RuntimeError("Databricks dbutils is required for secret lookup") from exc

    namespace = _conf("event_hubs.namespace")
    policy_name = _conf("event_hubs.sas_policy_name")
    policy_key = dbutils.secrets.get(
        scope=_conf("event_hubs.secret_scope"),
        key=_conf("event_hubs.secret_key"),
    )
    jaas = jaas_config(connection_string(namespace, policy_name, policy_key))
    return (
        _spark()
        .readStream.format("kafka")
        .option("kafka.bootstrap.servers", f"{namespace}.servicebus.windows.net:9093")
        .option("subscribe", _conf("event_hubs.topic"))
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "PLAIN")
        .option("kafka.sasl.jaas.config", jaas)
        .option("kafka.group.id", _conf("event_hubs.consumer_group"))
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "true")
        .load()
    )


@dp.table(
    name=TABLES.bronze_table,
    comment="Raw Canopy GPS events ingested from Azure Event Hubs.",
)
def gps_events():
    return bronze_rows(_event_hubs_stream())


@dp.table(
    name=TABLES.observations_table,
    comment="Validated and event_id-deduplicated Canopy GPS observations.",
)
def gps_observations():
    parsed = parse_bronze_rows(_spark().readStream.table(TABLES.bronze_table))
    return (
        valid_observation_rows(parsed)
        .withWatermark("event_time", "10 minutes")
        .dropDuplicatesWithinWatermark(["event_id"])
    )


@dp.table(
    name=TABLES.quarantine_table,
    comment="Malformed or unsupported Canopy GPS payloads.",
)
def gps_quarantine():
    parsed = parse_bronze_rows(_spark().readStream.table(TABLES.bronze_table))
    return quarantine_rows(parsed)


@dp.table(
    name=_STATEFUL_OUTPUT_TABLE,
    private=True,
    comment="Private tagged output from per-trip transformWithState processing.",
)
def canopy_gps_stateful_output():
    observations = _spark().readStream.table(TABLES.observations_table)
    return stateful_rows(observations)


@dp.table(
    name=TABLES.features_table,
    comment="Per-observation GPS motion features produced by the stateful runtime.",
)
def gps_features():
    from pyspark.sql import functions as F

    return (
        _spark()
        .readStream.table(_STATEFUL_OUTPUT_TABLE)
        .where(F.col("record_type") == "feature")
        .select(*FEATURE_COLUMNS)
    )


@dp.table(
    name=TABLES.segments_table,
    comment="Transportation-mode segments emitted by the first-layer detector.",
)
def mode_segments():
    from pyspark.sql import functions as F

    return (
        _spark()
        .readStream.table(_STATEFUL_OUTPUT_TABLE)
        .where(F.col("record_type") == "segment")
        .select(*SEGMENT_COLUMNS)
        .withColumnRenamed("processed_at", "emitted_at")
    )


@dp.foreach_batch_sink(name="canopy_speedtransformer_sink")
def canopy_speedtransformer_sink(batch_df, batch_id):
    """Run bounded SpeedTransformer inference for newly closed segments."""
    global _INFERENCE_HANDLER
    if _INFERENCE_HANDLER is None:
        # Prediction output remains an external Delta table because the
        # foreach-batch handler performs idempotent MERGE semantics. Creating
        # the table here is a runtime side effect, not pipeline-definition DDL.
        ensure_prediction_table(batch_df.sparkSession, _INFERENCE_CONFIG)
        _INFERENCE_HANDLER = build_foreach_batch_handler(
            batch_df.sparkSession,
            _INFERENCE_CONFIG,
        )
    _INFERENCE_HANDLER(batch_df, batch_id)


@dp.append_flow(
    name="canopy_speedtransformer_flow",
    target="canopy_speedtransformer_sink",
)
def canopy_speedtransformer_flow():
    return _spark().readStream.table(TABLES.segments_table).where("status = 'closed'")

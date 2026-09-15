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
from gps_streaming.spark_ingestion import (
    bronze_rows,
    parse_bronze_rows,
    quarantine_rows,
    valid_observation_rows,
)
from gps_streaming.transform_with_state import (
    TransformWithStateConfig,
    build_stateful_batch_handler,
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

# The checkpoint_location fields belong to the classic Structured Streaming
# compatibility adapters. Lakeflow owns checkpoints for these flows, so these
# sentinel values are never passed to a DataStreamWriter.
_STATEFUL_CONFIG = TransformWithStateConfig(
    checkpoint_location="lakeflow-managed",
    tables=TABLES,
)
_INFERENCE_CONFIG = DatabricksInferenceConfig(
    model_uri=_conf("model_uri"),
    checkpoint_location="lakeflow-managed",
    tables=TABLES,
)


def _ensure_foreach_batch_targets() -> None:
    """Create Delta tables owned by foreach-batch sinks before graph analysis.

    These tables are external to the Lakeflow graph: the stateful sink MERGEs
    features and segments into them, and the inference sink MERGEs predictions.
    Lakeflow resolves ``mode_segments`` as a streaming source while planning the
    graph, so the external target must already exist on the first update.
    """
    spark = _spark()
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLES.features_table} (
          schema_version STRING NOT NULL,
          event_id STRING NOT NULL,
          user_id STRING NOT NULL,
          device_id STRING NOT NULL,
          trip_id STRING NOT NULL,
          sequence BIGINT NOT NULL,
          event_time TIMESTAMP NOT NULL,
          received_at TIMESTAMP NOT NULL,
          lat DOUBLE NOT NULL,
          lon DOUBLE NOT NULL,
          accuracy DOUBLE,
          raw_speed DOUBLE,
          altitude_m DOUBLE,
          vertical_accuracy DOUBLE,
          previous_event_time TIMESTAMP,
          dt_s DOUBLE,
          distance_m DOUBLE,
          derived_speed_kmh DOUBLE,
          transition_valid BOOLEAN NOT NULL,
          invalid_reason STRING,
          speed_min_60s DOUBLE,
          processed_at TIMESTAMP NOT NULL
        ) USING DELTA
        """
    )
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLES.segments_table} (
          trip_id STRING NOT NULL,
          user_id STRING NOT NULL,
          segment_id STRING NOT NULL,
          start_time TIMESTAMP NOT NULL,
          end_time TIMESTAMP NOT NULL,
          speed_point_count INT NOT NULL,
          weak_mode STRING NOT NULL,
          weak_confidence DOUBLE NOT NULL,
          status STRING NOT NULL,
          detector_version STRING NOT NULL,
          emitted_at TIMESTAMP NOT NULL
        ) USING DELTA
        """
    )
    ensure_prediction_table(spark, _INFERENCE_CONFIG)


# ForEachBatch writes are outside Lakeflow-managed datasets. Create their Delta
# contracts before Lakeflow analyzes flows that read them. The DDL is
# idempotent because every statement uses CREATE TABLE IF NOT EXISTS.
_ensure_foreach_batch_targets()

_STATEFUL_HANDLER = build_stateful_batch_handler(_STATEFUL_CONFIG)
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
    connection_string = (
        f"Endpoint=sb://{namespace}.servicebus.windows.net/;"
        f"SharedAccessKeyName={policy_name};"
        f"SharedAccessKey={policy_key}"
    )
    escaped = connection_string.replace("\\", "\\\\").replace('"', '\\"')
    jaas = (
        "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required "
        'username="$ConnectionString" '
        f'password="{escaped}";'
    )
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


@dp.foreach_batch_sink(name="canopy_gps_stateful_sink")
def canopy_gps_stateful_sink(batch_df, batch_id):
    """Idempotently route tagged stateful output to features and segments."""
    _STATEFUL_HANDLER(batch_df, batch_id)


@dp.append_flow(
    name="canopy_gps_stateful_flow",
    target="canopy_gps_stateful_sink",
)
def canopy_gps_stateful_flow():
    observations = _spark().readStream.table(TABLES.observations_table)
    return stateful_rows(observations)


@dp.foreach_batch_sink(name="canopy_speedtransformer_sink")
def canopy_speedtransformer_sink(batch_df, batch_id):
    """Run bounded SpeedTransformer inference for newly closed segments."""
    global _INFERENCE_HANDLER
    if _INFERENCE_HANDLER is None:
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

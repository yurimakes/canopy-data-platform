"""Serverless Lakeflow pipeline definition for Canopy GPS streaming.

Lakeflow owns query lifecycle and checkpoints. The framework-neutral GPS core,
row-based transformWithState processor, and bounded SpeedTransformer inference
logic remain in their existing modules.
"""

from __future__ import annotations

from pathlib import Path
import sys

from pyspark import pipelines as dp


# The bundle sync root is ``cloud/azure/pipelines``. Ensure that importing the
# ``gps_streaming`` package works when this source file is evaluated by Lakeflow.
_PACKAGE_PARENT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from gps_streaming.databricks_adapter import (  # noqa: E402
    DatabricksInferenceConfig,
    build_foreach_batch_handler,
)
from gps_streaming.deployment_config import CanopyTableConfig  # noqa: E402
from gps_streaming.spark_ingestion import (  # noqa: E402
    bronze_rows,
    parse_bronze_rows,
    quarantine_rows,
    valid_observation_rows,
)
from gps_streaming.transform_with_state import (  # noqa: E402
    TransformWithStateConfig,
    build_stateful_batch_handler,
    stateful_rows,
)


def _conf(name: str) -> str:
    value = spark.conf.get(f"canopy.{name}")
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
_STATEFUL_HANDLER = build_stateful_batch_handler(_STATEFUL_CONFIG)
_INFERENCE_HANDLER = None


def _event_hubs_stream():
    """Build the Event Hubs Kafka source without putting secrets in config."""
    try:
        from databricks.sdk.runtime import dbutils
    except ImportError as exc:  # pragma: no cover - Databricks runtime boundary
        raise RuntimeError("Databricks dbutils is required for secret lookup") from exc

    connection_string = dbutils.secrets.get(
        scope=_conf("event_hubs.secret_scope"),
        key=_conf("event_hubs.secret_key"),
    )
    escaped = connection_string.replace("\\", "\\\\").replace('"', '\\"')
    jaas = (
        "org.apache.kafka.common.security.plain.PlainLoginModule required "
        'username="$ConnectionString" '
        f'password="{escaped}";'
    )
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", _conf("event_hubs.bootstrap_servers"))
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
    parsed = parse_bronze_rows(spark.readStream.table(TABLES.bronze_table))
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
    parsed = parse_bronze_rows(spark.readStream.table(TABLES.bronze_table))
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
    observations = spark.readStream.table(TABLES.observations_table)
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
    return (
        spark.readStream.table(TABLES.segments_table)
        .where("status = 'closed'")
    )

"""Databricks Jobs entry point for the complete Canopy GPS streaming graph."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


# The bundle sync root is ``cloud/azure/pipelines`` so direct execution sees
# this directory as the ``gps_streaming`` package. Normal repository imports
# continue to use the full namespace package.
if __package__:
    from .databricks_adapter import (
        DatabricksInferenceConfig,
        ensure_prediction_table,
        start_segment_inference_stream,
    )
    from .deployment_config import CanopyTableConfig
    from .spark_ingestion import (
        SparkIngestionConfig,
        ensure_upstream_tables,
        start_bronze_stream,
        start_parsed_streams,
    )
    from .transform_with_state import TransformWithStateConfig, start_stateful_stream
else:  # pragma: no cover - exercised by Databricks spark_python_task
    package_parent = Path(__file__).resolve().parent.parent
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))
    from gps_streaming.databricks_adapter import (
        DatabricksInferenceConfig,
        ensure_prediction_table,
        start_segment_inference_stream,
    )
    from gps_streaming.deployment_config import CanopyTableConfig
    from gps_streaming.spark_ingestion import (
        SparkIngestionConfig,
        ensure_upstream_tables,
        start_bronze_stream,
        start_parsed_streams,
    )
    from gps_streaming.transform_with_state import (
        TransformWithStateConfig,
        start_stateful_stream,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--bronze-schema", required=True)
    parser.add_argument("--silver-schema", required=True)
    parser.add_argument("--gold-schema", required=True)
    parser.add_argument("--bronze-events-table", required=True)
    parser.add_argument("--observations-table", required=True)
    parser.add_argument("--quarantine-table", required=True)
    parser.add_argument("--features-table", required=True)
    parser.add_argument("--segments-table", required=True)
    parser.add_argument("--predictions-table", required=True)
    parser.add_argument("--checkpoint-root", required=True)
    parser.add_argument("--event-hubs-bootstrap-servers", required=True)
    parser.add_argument("--event-hubs-topic", required=True)
    parser.add_argument("--event-hubs-consumer-group", required=True)
    parser.add_argument("--event-hubs-secret-scope", required=True)
    parser.add_argument("--event-hubs-secret-key", required=True)
    parser.add_argument("--model-uri", required=True)
    parser.add_argument("--trigger-interval", default="10 seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    tables = CanopyTableConfig(
        catalog=args.catalog,
        bronze_schema=args.bronze_schema,
        silver_schema=args.silver_schema,
        gold_schema=args.gold_schema,
        bronze_events_name=args.bronze_events_table,
        observations_name=args.observations_table,
        quarantine_name=args.quarantine_table,
        features_name=args.features_table,
        segments_name=args.segments_table,
        predictions_name=args.predictions_table,
    )
    checkpoint_root = args.checkpoint_root.rstrip("/")
    ingestion = SparkIngestionConfig(
        bronze_checkpoint=f"{checkpoint_root}/bronze",
        observations_checkpoint=f"{checkpoint_root}/observations",
        quarantine_checkpoint=f"{checkpoint_root}/quarantine",
        tables=tables,
    )
    stateful = TransformWithStateConfig(
        checkpoint_location=f"{checkpoint_root}/features-and-segments",
        tables=tables,
    )
    inference = DatabricksInferenceConfig(
        model_uri=args.model_uri,
        checkpoint_location=f"{checkpoint_root}/segment-inference",
        tables=tables,
    )

    ensure_upstream_tables(spark, ingestion)
    ensure_prediction_table(spark, inference)
    kafka_events = event_hubs_stream(spark, args)

    queries = [
        start_bronze_stream(
            kafka_events, ingestion, trigger_interval=args.trigger_interval
        ),
        *start_parsed_streams(
            spark, ingestion, trigger_interval=args.trigger_interval
        ),
        start_stateful_stream(
            spark, stateful, trigger_interval=args.trigger_interval
        ),
        start_segment_inference_stream(
            spark, inference, trigger_interval=args.trigger_interval
        ),
    ]
    if len(queries) != 5:
        raise AssertionError("expected all five Canopy streaming queries")
    spark.streams.awaitAnyTermination()


def event_hubs_stream(spark, args):
    """Create a Kafka-compatible Event Hubs source without exposing its secret."""
    try:
        from databricks.sdk.runtime import dbutils
    except ImportError as exc:  # pragma: no cover - Databricks runtime boundary
        raise RuntimeError("Databricks dbutils is required for secret lookup") from exc

    connection_string = dbutils.secrets.get(
        scope=args.event_hubs_secret_scope,
        key=args.event_hubs_secret_key,
    )
    escaped = connection_string.replace("\\", "\\\\").replace('"', '\\"')
    jaas = (
        "org.apache.kafka.common.security.plain.PlainLoginModule required "
        'username="$ConnectionString" '
        f'password="{escaped}";'
    )
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", args.event_hubs_bootstrap_servers)
        .option("subscribe", args.event_hubs_topic)
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "PLAIN")
        .option("kafka.sasl.jaas.config", jaas)
        .option("kafka.group.id", args.event_hubs_consumer_group)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "true")
        .load()
    )


if __name__ == "__main__":
    main()

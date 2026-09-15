"""Stable PySpark contracts before runtime-specific stateful processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .deployment_config import CanopyTableConfig


@dataclass(frozen=True)
class SparkIngestionConfig:
    """Names and checkpoints supplied through deployment configuration."""

    bronze_checkpoint: str
    observations_checkpoint: str
    quarantine_checkpoint: str
    tables: CanopyTableConfig = field(default_factory=CanopyTableConfig)

    def __post_init__(self) -> None:
        for value in (
            self.bronze_checkpoint,
            self.observations_checkpoint,
            self.quarantine_checkpoint,
        ):
            if not value.strip():
                raise ValueError("all checkpoint locations are required")

    @property
    def bronze_table(self) -> str:
        return self.tables.bronze_table

    @property
    def observations_table(self) -> str:
        return self.tables.observations_table

    @property
    def quarantine_table(self) -> str:
        return self.tables.quarantine_table

    @property
    def features_table(self) -> str:
        return self.tables.features_table

    @property
    def segments_table(self) -> str:
        return self.tables.segments_table


def table_ddl(config: SparkIngestionConfig) -> tuple[str, ...]:
    """Return the upstream Delta contracts in dependency order."""
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {config.bronze_table} (
          body STRING NOT NULL,
          event_hub_topic STRING,
          event_hub_partition INT,
          event_hub_offset BIGINT,
          event_hub_enqueued_at TIMESTAMP,
          ingested_at TIMESTAMP NOT NULL
        ) USING DELTA
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {config.observations_table} (
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
          event_hub_enqueued_at TIMESTAMP,
          bronze_ingested_at TIMESTAMP NOT NULL,
          parsed_at TIMESTAMP NOT NULL
        ) USING DELTA
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {config.quarantine_table} (
          body STRING NOT NULL,
          rejection_reason STRING NOT NULL,
          event_hub_enqueued_at TIMESTAMP,
          bronze_ingested_at TIMESTAMP NOT NULL,
          quarantined_at TIMESTAMP NOT NULL
        ) USING DELTA
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {config.features_table} (
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
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {config.segments_table} (
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
        """,
    )


def ensure_upstream_tables(spark: Any, config: SparkIngestionConfig) -> None:
    for statement in table_ddl(config):
        spark.sql(statement)


def gps_payload_schema() -> Any:
    """Return the intended collector payload schema without importing PySpark locally."""
    from pyspark.sql.types import (
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    return StructType(
        [
            StructField("schema_version", StringType(), True),
            StructField("event_id", StringType(), True),
            StructField("user_id", StringType(), True),
            StructField("device_id", StringType(), True),
            StructField("trip_id", StringType(), True),
            StructField("sequence", LongType(), True),
            StructField("event_time", TimestampType(), True),
            StructField("received_at", TimestampType(), True),
            StructField("lat", DoubleType(), True),
            StructField("lon", DoubleType(), True),
            StructField("accuracy", DoubleType(), True),
            StructField("speed", DoubleType(), True),
            StructField("altitude_m", DoubleType(), True),
            StructField("vertical_accuracy", DoubleType(), True),
            StructField("_corrupt_record", StringType(), True),
        ]
    )


def bronze_rows(kafka_events: Any) -> Any:
    """Map the Event Hubs Kafka-compatible envelope to the Bronze contract."""
    from pyspark.sql import functions as F

    return kafka_events.select(
        F.col("value").cast("string").alias("body"),
        F.col("topic").alias("event_hub_topic"),
        F.col("partition").cast("int").alias("event_hub_partition"),
        F.col("offset").cast("long").alias("event_hub_offset"),
        F.col("timestamp").alias("event_hub_enqueued_at"),
        F.current_timestamp().alias("ingested_at"),
    )


def parse_bronze_rows(bronze_events: Any) -> Any:
    """Parse JSON and attach one deterministic rejection reason per row."""
    from pyspark.sql import functions as F

    parsed = F.from_json(
        F.col("body"),
        gps_payload_schema(),
        {"mode": "PERMISSIVE", "columnNameOfCorruptRecord": "_corrupt_record"},
    )
    frame = bronze_events.withColumn("payload", parsed)
    required = (
        "schema_version",
        "event_id",
        "user_id",
        "device_id",
        "trip_id",
        "sequence",
        "event_time",
        "received_at",
        "lat",
        "lon",
    )
    missing_required = F.array_join(
        F.array_compact(
            F.array(
                *(F.when(F.col(f"payload.{name}").isNull(), F.lit(name)) for name in required)
            )
        ),
        ",",
    )
    reason = (
        F.when(F.col("payload._corrupt_record").isNotNull(), F.lit("malformed_json"))
        .when(F.length(missing_required) > 0, F.concat(F.lit("missing_required:"), missing_required))
        .when(
            F.col("payload.schema_version") != F.lit("canopy.gps.collector.v0.1"),
            F.lit("unsupported_schema_version"),
        )
        .when(~F.col("payload.lat").between(-90.0, 90.0), F.lit("invalid_lat"))
        .when(~F.col("payload.lon").between(-180.0, 180.0), F.lit("invalid_lon"))
        .when(F.col("payload.sequence") < 0, F.lit("invalid_sequence"))
    )
    return frame.withColumn("rejection_reason", reason)


def valid_observation_rows(parsed_events: Any) -> Any:
    """Project validated records and keep the raw speed unit intentionally unnamed."""
    from pyspark.sql import functions as F

    return (
        parsed_events.where(F.col("rejection_reason").isNull())
        .select(
            "payload.schema_version",
            "payload.event_id",
            "payload.user_id",
            "payload.device_id",
            "payload.trip_id",
            "payload.sequence",
            "payload.event_time",
            "payload.received_at",
            "payload.lat",
            "payload.lon",
            "payload.accuracy",
            F.col("payload.speed").alias("raw_speed"),
            "payload.altitude_m",
            "payload.vertical_accuracy",
            "event_hub_enqueued_at",
            F.col("ingested_at").alias("bronze_ingested_at"),
            F.current_timestamp().alias("parsed_at"),
        )
    )


def quarantine_rows(parsed_events: Any) -> Any:
    from pyspark.sql import functions as F

    return parsed_events.where(F.col("rejection_reason").isNotNull()).select(
        "body",
        "rejection_reason",
        "event_hub_enqueued_at",
        F.col("ingested_at").alias("bronze_ingested_at"),
        F.current_timestamp().alias("quarantined_at"),
    )


def start_bronze_stream(
    kafka_events: Any,
    config: SparkIngestionConfig,
    *,
    trigger_interval: str = "10 seconds",
) -> Any:
    return (
        bronze_rows(kafka_events)
        .writeStream.queryName("canopy-gps-bronze")
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", config.bronze_checkpoint)
        .trigger(processingTime=trigger_interval)
        .toTable(config.bronze_table)
    )


def start_parsed_streams(
    spark: Any,
    config: SparkIngestionConfig,
    *,
    watermark: str = "10 minutes",
    trigger_interval: str = "10 seconds",
) -> tuple[Any, Any]:
    """Start independent valid/quarantine consumers of the durable Bronze table."""
    source = spark.readStream.table(config.bronze_table)
    parsed = parse_bronze_rows(source)
    valid = (
        valid_observation_rows(parsed)
        .withWatermark("event_time", watermark)
        .dropDuplicates(["event_id"])
    )
    valid_query = (
        valid.writeStream.queryName("canopy-gps-observations")
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", config.observations_checkpoint)
        .trigger(processingTime=trigger_interval)
        .toTable(config.observations_table)
    )
    quarantine_query = (
        quarantine_rows(parsed)
        .writeStream.queryName("canopy-gps-quarantine")
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", config.quarantine_checkpoint)
        .trigger(processingTime=trigger_interval)
        .toTable(config.quarantine_table)
    )
    return valid_query, quarantine_query

"""Generic Event Hubs ingestion projections and primitive event routing."""

from __future__ import annotations

from typing import Any

from gps_ingestion.spark_ingestion import SUPPORTED_SCHEMA_VERSIONS


GENERIC_BRONZE_SCHEMA_DDL = """
raw_payload STRING NOT NULL,
event_id STRING,
event_type STRING,
schema_version STRING,
event_hub_topic STRING,
event_hub_partition INT,
event_hub_offset BIGINT,
event_hub_enqueued_at TIMESTAMP,
ingested_at TIMESTAMP NOT NULL
"""

TRIP_ENDED_SCHEMA_DDL = """
event_id STRING NOT NULL,
event_type STRING NOT NULL,
schema_version STRING NOT NULL,
trip_id STRING NOT NULL,
user_id STRING NOT NULL,
campaign_id STRING NOT NULL,
started_at TIMESTAMP NOT NULL,
ended_at TIMESTAMP NOT NULL,
expected_last_sequence BIGINT NOT NULL,
occurred_at TIMESTAMP NOT NULL,
processing_generation BIGINT NOT NULL,
result_owner STRING NOT NULL,
event_hub_topic STRING,
event_hub_partition INT,
event_hub_offset BIGINT,
event_hub_enqueued_at TIMESTAMP,
bronze_ingested_at TIMESTAMP NOT NULL,
parsed_at TIMESTAMP NOT NULL
"""

_TRIP_EVENT_TYPE = "trip_ended"
_TRIP_SCHEMA_VERSION = "trip-lifecycle-v1"
_UUID_PATTERN = r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _variant_get(payload_column: str, field: str, target_type: str) -> Any:
    from pyspark.sql import functions as F

    return F.expr(
        f"try_variant_get(`{payload_column}`, '$.{field}', '{target_type}')"
    )


def generic_bronze_rows(kafka_events: Any) -> Any:
    """Preserve every Event Hubs body while extracting only routing metadata."""
    from pyspark.sql import functions as F

    frame = kafka_events.select(
        F.col("value").cast("string").alias("raw_payload"),
        F.col("topic").alias("event_hub_topic"),
        F.col("partition").cast("int").alias("event_hub_partition"),
        F.col("offset").cast("long").alias("event_hub_offset"),
        F.col("timestamp").alias("event_hub_enqueued_at"),
        F.current_timestamp().alias("ingested_at"),
    ).withColumn("_payload", F.expr("try_parse_json(raw_payload)"))

    for field in ("event_id", "event_type", "schema_version"):
        frame = frame.withColumn(
            field,
            _variant_get("_payload", field, "string"),
        )

    return frame.drop("_payload")


def gps_parser_input_rows(bronze_events: Any) -> Any:
    """Route supported GPS schemas and adapt generic Bronze to the legacy parser."""
    from pyspark.sql import functions as F

    return bronze_events.where(
        F.col("schema_version").isin(*SUPPORTED_SCHEMA_VERSIONS)
    ).select(
        F.col("raw_payload").alias("body"),
        "event_hub_topic",
        "event_hub_partition",
        "event_hub_offset",
        "event_hub_enqueued_at",
        "ingested_at",
    )


def trip_ended_rows(bronze_events: Any) -> Any:
    """Validate and project trip-lifecycle-v1 trip_ended events for finalization."""
    from pyspark.sql import functions as F

    routed = bronze_events.where(
        (F.col("event_type") == _TRIP_EVENT_TYPE)
        & (F.col("schema_version") == _TRIP_SCHEMA_VERSION)
    ).withColumn("_payload", F.expr("try_parse_json(raw_payload)"))

    string_fields = (
        "event_id",
        "event_type",
        "schema_version",
        "trip_id",
        "user_id",
        "campaign_id",
        "started_at",
        "ended_at",
        "occurred_at",
        "result_owner",
    )
    integer_fields = ("expected_last_sequence", "processing_generation")

    for field in string_fields + integer_fields:
        routed = routed.withColumn(
            f"_raw_{field}",
            _variant_get("_payload", field, "variant"),
        ).withColumn(
            f"_schema_{field}",
            F.expr(f"schema_of_variant(`_raw_{field}`)"),
        )

    for field in string_fields:
        routed = routed.withColumn(
            f"_{field}_text",
            _variant_get("_payload", field, "string"),
        )
    for field in integer_fields:
        routed = routed.withColumn(
            f"_{field}_number",
            _variant_get("_payload", field, "bigint"),
        )

    routed = (
        routed
        .withColumn("_started_at_ts", F.try_to_timestamp(F.col("_started_at_text")))
        .withColumn("_ended_at_ts", F.try_to_timestamp(F.col("_ended_at_text")))
        .withColumn("_occurred_at_ts", F.try_to_timestamp(F.col("_occurred_at_text")))
    )

    strings_have_correct_type = F.lit(True)
    for field in string_fields:
        strings_have_correct_type = strings_have_correct_type & (
            F.col(f"_schema_{field}") == F.lit("STRING")
        )

    integers_have_correct_type = F.lit(True)
    for field in integer_fields:
        integers_have_correct_type = integers_have_correct_type & (
            F.col(f"_schema_{field}") == F.lit("BIGINT")
        )

    valid = (
        F.col("_event_id_text").rlike(_UUID_PATTERN)
        & (F.col("_event_type_text") == F.lit(_TRIP_EVENT_TYPE))
        & (F.col("_schema_version_text") == F.lit(_TRIP_SCHEMA_VERSION))
        & (F.length(F.trim(F.col("_trip_id_text"))) > 0)
        & (F.length(F.trim(F.col("_user_id_text"))) > 0)
        & (F.length(F.trim(F.col("_campaign_id_text"))) > 0)
        & F.col("_started_at_ts").isNotNull()
        & F.col("_ended_at_ts").isNotNull()
        & F.col("_occurred_at_ts").isNotNull()
        & F.col("_expected_last_sequence_number").between(0, 10_000_000)
        & (F.col("_processing_generation_number") >= 1)
        & F.col("_result_owner_text").isin("functions", "databricks")
        & strings_have_correct_type
        & integers_have_correct_type
    )

    return routed.where(valid).select(
        F.col("_event_id_text").alias("event_id"),
        F.col("_event_type_text").alias("event_type"),
        F.col("_schema_version_text").alias("schema_version"),
        F.col("_trip_id_text").alias("trip_id"),
        F.col("_user_id_text").alias("user_id"),
        F.col("_campaign_id_text").alias("campaign_id"),
        F.col("_started_at_ts").alias("started_at"),
        F.col("_ended_at_ts").alias("ended_at"),
        F.col("_expected_last_sequence_number").alias("expected_last_sequence"),
        F.col("_occurred_at_ts").alias("occurred_at"),
        F.col("_processing_generation_number").alias("processing_generation"),
        F.col("_result_owner_text").alias("result_owner"),
        "event_hub_topic",
        "event_hub_partition",
        "event_hub_offset",
        "event_hub_enqueued_at",
        F.col("ingested_at").alias("bronze_ingested_at"),
        F.current_timestamp().alias("parsed_at"),
    )


def deduplicate_event_ids(events: Any, watermark: str) -> Any:
    """Bound duplicate event_id state by Event Hubs enqueue time."""
    if not watermark or not watermark.strip():
        raise ValueError("deduplication watermark is required")
    return events.withWatermark(
        "event_hub_enqueued_at", watermark.strip()
    ).dropDuplicatesWithinWatermark(["event_id"])

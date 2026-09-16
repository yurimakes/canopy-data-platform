"""Spark-native schemas, projections, and validation for GPS Pipeline A.

This module deliberately contains no streaming writers, checkpoints, triggers,
or table-creation side effects. Lakeflow owns those concerns.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_SCHEMA_VERSIONS = (
    "canopy.gps.collector.v0.1",
    "canopy.gps.collector.v0.2",
)

REQUIRED_COLLECTOR_FIELDS = (
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
    "accuracy",
    "speed",
    "altitude_m",
    "vertical_accuracy_m",
    "course_deg",
    "source",
    "quality_flags",
    "raw_location",
)

BRONZE_SCHEMA_DDL = """
body STRING NOT NULL,
event_hub_topic STRING,
event_hub_partition INT,
event_hub_offset BIGINT,
event_hub_enqueued_at TIMESTAMP,
ingested_at TIMESTAMP NOT NULL
"""

OBSERVATIONS_SCHEMA_DDL = """
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
vertical_accuracy_m DOUBLE,
course_deg DOUBLE,
source STRING NOT NULL,
quality_flags ARRAY<STRING> NOT NULL,
collection_mode STRING,
label STRING,
event_hub_topic STRING,
event_hub_partition INT,
event_hub_offset BIGINT,
event_hub_enqueued_at TIMESTAMP,
bronze_ingested_at TIMESTAMP NOT NULL,
parsed_at TIMESTAMP NOT NULL
"""

QUARANTINE_SCHEMA_DDL = """
body STRING NOT NULL,
schema_version STRING,
event_id STRING,
rejection_reason STRING NOT NULL,
rejection_reasons ARRAY<STRING> NOT NULL,
event_hub_topic STRING,
event_hub_partition INT,
event_hub_offset BIGINT,
event_hub_enqueued_at TIMESTAMP,
bronze_ingested_at TIMESTAMP NOT NULL,
quarantined_at TIMESTAMP NOT NULL
"""

_ALL_COLLECTOR_FIELDS = REQUIRED_COLLECTOR_FIELDS + ("collection_mode", "label")
_STRING_FIELDS = (
    "schema_version",
    "event_id",
    "user_id",
    "device_id",
    "trip_id",
    "event_time",
    "received_at",
    "source",
)
_UUID_FIELDS = ("event_id", "user_id", "device_id", "trip_id")
_NULLABLE_NUMERIC_FIELDS = (
    "accuracy",
    "speed",
    "altitude_m",
    "vertical_accuracy_m",
    "course_deg",
)
_UUID_PATTERN = r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_UTC_TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
_NUMBER_SCHEMA_PATTERN = r"^(?:TINYINT|SMALLINT|INT|BIGINT|FLOAT|DOUBLE|DECIMAL\(\d+,\d+\))$"


def bronze_rows(kafka_events: Any) -> Any:
    """Project a Kafka-compatible Event Hubs envelope without changing its body."""
    from pyspark.sql import functions as F

    return kafka_events.select(
        F.col("value").cast("string").alias("body"),
        F.col("topic").alias("event_hub_topic"),
        F.col("partition").cast("int").alias("event_hub_partition"),
        F.col("offset").cast("long").alias("event_hub_offset"),
        F.col("timestamp").alias("event_hub_enqueued_at"),
        F.current_timestamp().alias("ingested_at"),
    )


def _variant_get(payload: Any, field: str, target_type: str) -> Any:
    from pyspark.sql import functions as F

    return F.try_variant_get(payload, f"$.{field}", target_type)


def _reason(condition: Any, value: Any) -> Any:
    from pyspark.sql import functions as F

    literal = F.lit(value) if isinstance(value, str) else value
    return F.when(condition, literal)


def parse_bronze_rows(bronze_events: Any) -> Any:
    """Parse and fully validate the authoritative collector contract.

    VARIANT preserves the distinctions between an absent path, explicit JSON
    null, a wrong JSON type, and an invalid value. The result contains canonical
    values and an ordered array of every rejection reason.
    """
    from pyspark.sql import functions as F

    frame = bronze_events.withColumn("_payload", F.try_parse_json(F.col("body")))
    frame = frame.withColumn("_payload_schema", F.schema_of_variant(F.col("_payload")))
    is_object = F.col("_payload_schema").startswith("OBJECT<")

    for field in _ALL_COLLECTOR_FIELDS:
        raw_name = f"_raw_{field}"
        frame = frame.withColumn(raw_name, _variant_get(F.col("_payload"), field, "variant"))
        frame = frame.withColumn(f"_schema_{field}", F.schema_of_variant(F.col(raw_name)))

    def raw(field: str) -> Any:
        return F.col(f"_raw_{field}")

    def value_schema(field: str) -> Any:
        return F.col(f"_schema_{field}")

    def present(field: str) -> Any:
        return raw(field).isNotNull()

    def json_null(field: str) -> Any:
        return F.coalesce(F.is_variant_null(raw(field)), F.lit(False))

    def is_string(field: str) -> Any:
        return value_schema(field) == F.lit("STRING")

    def is_number(field: str) -> Any:
        return value_schema(field).rlike(_NUMBER_SCHEMA_PATTERN)

    for field in _STRING_FIELDS + ("collection_mode", "label"):
        frame = frame.withColumn(
            f"_{field}_text", _variant_get(F.col("_payload"), field, "string")
        )
    for field in ("lat", "lon") + _NULLABLE_NUMERIC_FIELDS:
        frame = frame.withColumn(
            f"_{field}_number", _variant_get(F.col("_payload"), field, "double")
        )
    frame = frame.withColumn(
        "_sequence_number", _variant_get(F.col("_payload"), "sequence", "bigint")
    )
    frame = frame.withColumn(
        "_quality_flags",
        _variant_get(F.col("_payload"), "quality_flags", "array<string>"),
    )
    frame = frame.withColumn(
        "_event_time_timestamp", F.try_to_timestamp(F.col("_event_time_text"))
    )
    frame = frame.withColumn(
        "_received_at_timestamp", F.try_to_timestamp(F.col("_received_at_text"))
    )

    schema_version = F.col("_schema_version_text")
    is_v01 = is_string("schema_version") & (
        schema_version == F.lit(SUPPORTED_SCHEMA_VERSIONS[0])
    )
    is_v02 = is_string("schema_version") & (
        schema_version == F.lit(SUPPORTED_SCHEMA_VERSIONS[1])
    )

    missing_columns = [
        F.when(is_object & ~present(field), F.lit(field))
        for field in REQUIRED_COLLECTOR_FIELDS
    ]
    missing_columns.extend(
        [
            F.when(is_object & is_v02 & ~present("collection_mode"), F.lit("collection_mode")),
            F.when(is_object & is_v02 & ~present("label"), F.lit("label")),
        ]
    )
    missing_fields = F.array_compact(F.array(*missing_columns))
    missing_reason = F.concat(
        F.lit("missing_required:"), F.array_join(missing_fields, ",")
    )

    malformed = F.col("_payload").isNull()
    invalid_top_level = ~malformed & ~is_object
    has_missing = is_object & (F.size(missing_fields) > F.lit(0))
    supported_version = schema_version.isin(*SUPPORTED_SCHEMA_VERSIONS)

    reasons = [
        _reason(malformed, "malformed_json"),
        _reason(invalid_top_level, "invalid_top_level_type"),
        _reason(has_missing, missing_reason),
        _reason(
            is_object
            & present("schema_version")
            & is_string("schema_version")
            & ~supported_version,
            "unsupported_schema_version",
        ),
    ]

    for field in _STRING_FIELDS:
        reasons.append(
            _reason(is_object & present(field) & ~is_string(field), f"invalid_type:{field}")
        )
    reasons.append(
        _reason(
            is_object & present("sequence") & (value_schema("sequence") != F.lit("BIGINT")),
            "invalid_type:sequence",
        )
    )
    for field in ("lat", "lon"):
        reasons.append(
            _reason(is_object & present(field) & ~is_number(field), f"invalid_type:{field}")
        )
    for field in _NULLABLE_NUMERIC_FIELDS:
        reasons.append(
            _reason(
                is_object & present(field) & ~(json_null(field) | is_number(field)),
                f"invalid_type:{field}",
            )
        )

    quality_is_array = value_schema("quality_flags").startswith("ARRAY<")
    reasons.append(
        _reason(
            is_object & present("quality_flags") & ~quality_is_array,
            "invalid_type:quality_flags",
        )
    )
    reasons.append(
        _reason(
            is_object & present("collection_mode") & ~is_string("collection_mode"),
            "invalid_type:collection_mode",
        )
    )
    label_has_valid_json_type = is_string("label") | json_null("label")
    reasons.append(
        _reason(
            is_object & present("label") & ~label_has_valid_json_type,
            "invalid_type:label",
        )
    )

    for field in _UUID_FIELDS:
        reasons.append(
            _reason(
                is_object
                & present(field)
                & is_string(field)
                & ~F.col(f"_{field}_text").rlike(_UUID_PATTERN),
                f"invalid_uuid:{field}",
            )
        )
    for field in ("event_time", "received_at"):
        reasons.append(
            _reason(
                is_object
                & present(field)
                & is_string(field)
                & (
                    ~F.col(f"_{field}_text").rlike(_UTC_TIMESTAMP_PATTERN)
                    | F.col(f"_{field}_timestamp").isNull()
                ),
                f"invalid_timestamp:{field}",
            )
        )

    reasons.extend(
        [
            _reason(
                is_object & present("lat") & is_number("lat")
                & ~F.col("_lat_number").between(-90.0, 90.0),
                "invalid_lat",
            ),
            _reason(
                is_object & present("lon") & is_number("lon")
                & ~F.col("_lon_number").between(-180.0, 180.0),
                "invalid_lon",
            ),
            _reason(
                is_object & present("sequence")
                & (value_schema("sequence") == F.lit("BIGINT"))
                & (F.col("_sequence_number").isNull() | (F.col("_sequence_number") < 1)),
                "invalid_sequence",
            ),
            _reason(
                is_object & present("accuracy") & is_number("accuracy")
                & (F.col("_accuracy_number") < 0.0),
                "invalid_accuracy",
            ),
            _reason(
                is_object & present("speed") & is_number("speed")
                & (F.col("_speed_number") < 0.0),
                "invalid_speed",
            ),
            _reason(
                is_object & present("vertical_accuracy_m")
                & is_number("vertical_accuracy_m")
                & (F.col("_vertical_accuracy_m_number") < 0.0),
                "invalid_vertical_accuracy_m",
            ),
            _reason(
                is_object & present("course_deg") & is_number("course_deg")
                & ((F.col("_course_deg_number") < 0.0) | (F.col("_course_deg_number") >= 360.0)),
                "invalid_course_deg",
            ),
            _reason(
                is_object & present("source") & is_string("source")
                & ~F.col("_source_text").isin(
                    "expo-location.foreground", "expo-location.background"
                ),
                "invalid_source",
            ),
        ]
    )

    quality_items_are_strings = value_schema("quality_flags").isin(
        "ARRAY<STRING>", "ARRAY<VOID>"
    )
    quality_has_duplicates = F.col("_quality_flags").isNotNull() & (
        F.size(F.array_distinct(F.col("_quality_flags")))
        != F.size(F.col("_quality_flags"))
    )
    reasons.append(
        _reason(
            is_object & present("quality_flags") & quality_is_array
            & (~quality_items_are_strings | quality_has_duplicates),
            "invalid_quality_flags",
        )
    )
    reasons.append(
        _reason(
            is_object & present("raw_location")
            & ~value_schema("raw_location").startswith("OBJECT<"),
            "invalid_raw_location",
        )
    )

    collection_mode = F.col("_collection_mode_text")
    label = F.col("_label_text")
    mode_value_valid = collection_mode.isin("user", "developer")
    reasons.append(
        _reason(
            is_object & present("collection_mode") & is_string("collection_mode")
            & ~mode_value_valid,
            "invalid_collection_mode",
        )
    )
    v01_label_valid = label.isin("walking", "cycling", "car", "bus", "subway")
    v02_label_valid = label.isin("walk", "bike", "car", "bus", "rail")
    reasons.append(
        _reason(
            is_object & present("label")
            & (
                (is_v01 & (~is_string("label") | ~v01_label_valid))
                | (is_v02 & is_string("label") & ~v02_label_valid)
            ),
            "invalid_label",
        )
    )
    reasons.append(
        _reason(
            is_object & is_v02 & present("collection_mode") & present("label")
            & is_string("collection_mode") & mode_value_valid
            & label_has_valid_json_type
            & (
                ((collection_mode == F.lit("user")) & ~json_null("label"))
                | ((collection_mode == F.lit("developer"))
                   & ~(is_string("label") & v02_label_valid))
            ),
            "incompatible_collection_mode_label",
        )
    )

    frame = frame.withColumn(
        "rejection_reasons", F.array_compact(F.array(*reasons))
    )
    frame = frame.withColumn(
        "rejection_reason", F.element_at(F.col("rejection_reasons"), F.lit(1))
    )

    return frame.select(
        "body",
        "event_hub_topic",
        "event_hub_partition",
        "event_hub_offset",
        "event_hub_enqueued_at",
        "ingested_at",
        F.when(is_string("schema_version"), schema_version).alias("schema_version"),
        F.when(is_string("event_id"), F.col("_event_id_text")).alias("event_id"),
        F.col("_user_id_text").alias("user_id"),
        F.col("_device_id_text").alias("device_id"),
        F.col("_trip_id_text").alias("trip_id"),
        F.col("_sequence_number").alias("sequence"),
        F.col("_event_time_timestamp").alias("event_time"),
        F.col("_received_at_timestamp").alias("received_at"),
        F.col("_lat_number").alias("lat"),
        F.col("_lon_number").alias("lon"),
        F.col("_accuracy_number").alias("accuracy"),
        F.col("_speed_number").alias("raw_speed"),
        F.col("_altitude_m_number").alias("altitude_m"),
        F.col("_vertical_accuracy_m_number").alias("vertical_accuracy_m"),
        F.col("_course_deg_number").alias("course_deg"),
        F.col("_source_text").alias("source"),
        F.col("_quality_flags").alias("quality_flags"),
        F.when(is_string("collection_mode"), collection_mode).alias("collection_mode"),
        F.when(is_string("label"), label).alias("label"),
        "rejection_reason",
        "rejection_reasons",
        F.current_timestamp().alias("parsed_at"),
    )


def valid_observation_rows(parsed_events: Any) -> Any:
    """Project valid collector events to the approved Silver contract."""
    from pyspark.sql import functions as F

    return parsed_events.where(F.size(F.col("rejection_reasons")) == 0).select(
        "schema_version", "event_id", "user_id", "device_id", "trip_id", "sequence",
        "event_time", "received_at", "lat", "lon", "accuracy", "raw_speed",
        "altitude_m", "vertical_accuracy_m", "course_deg", "source", "quality_flags",
        "collection_mode", "label", "event_hub_topic", "event_hub_partition",
        "event_hub_offset", "event_hub_enqueued_at",
        F.col("ingested_at").alias("bronze_ingested_at"), "parsed_at",
    )


def quarantine_rows(parsed_events: Any) -> Any:
    """Project rejected rows with their raw body and Event Hubs provenance."""
    from pyspark.sql import functions as F

    return parsed_events.where(F.size(F.col("rejection_reasons")) > 0).select(
        "body", "schema_version", "event_id", "rejection_reason", "rejection_reasons",
        "event_hub_topic", "event_hub_partition", "event_hub_offset",
        "event_hub_enqueued_at", F.col("ingested_at").alias("bronze_ingested_at"),
        F.current_timestamp().alias("quarantined_at"),
    )


def deduplicate_observations(observations: Any, watermark: str) -> Any:
    """Apply bounded event-id deduplication using Event Hubs enqueue time."""
    if not watermark or not watermark.strip():
        raise ValueError("deduplication watermark is required")
    return observations.withWatermark(
        "event_hub_enqueued_at", watermark.strip()
    ).dropDuplicatesWithinWatermark(["event_id"])

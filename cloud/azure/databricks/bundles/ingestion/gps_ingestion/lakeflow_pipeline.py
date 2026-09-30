"""Lakeflow declaration for generic Event Hubs ingestion and primitive routing."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from gps_ingestion.deployment_config import EventIngestionTableConfig
from gps_ingestion.event_hubs_auth import connection_string, jaas_config
from gps_ingestion.event_ingestion import (
    GENERIC_BRONZE_SCHEMA_DDL,
    TRIP_ENDED_SCHEMA_DDL,
    deduplicate_event_ids,
    generic_bronze_rows,
    gps_parser_input_rows,
    trip_ended_rows,
)
from gps_ingestion.spark_ingestion import (
    OBSERVATIONS_SCHEMA_DDL,
    QUARANTINE_SCHEMA_DDL,
    deduplicate_observations,
    parse_bronze_rows,
    quarantine_rows,
    valid_observation_rows,
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


def _bool_conf(name: str, default: bool = False) -> bool:
    value = _spark().conf.get(f"canopy.{name}", str(default).lower())
    return value.strip().lower() in {"1", "true", "yes", "on"}


TABLES = EventIngestionTableConfig(
    catalog=_conf("catalog"),
    bronze_schema=_conf("bronze_schema"),
    silver_schema=_conf("silver_schema"),
    bronze_events_name=_conf("bronze_events_table"),
    gps_observations_name=_conf("gps_observations_table"),
    gps_quarantine_name=_conf("gps_quarantine_table"),
    trip_ended_events_name=_conf("trip_ended_events_table"),
)
DEDUPLICATION_WATERMARK = _conf("deduplication_watermark")
APPLY_DEDUPLICATION = _bool_conf("apply_deduplication", default=True)
FUSE_GPS_PARSE_VALIDATION = _bool_conf("fuse_gps_parse_validation")
DIRECT_EVENTHUB_FANOUT = _bool_conf("direct_eventhub_fanout")
_GPS_PARSED_TABLE = "gps_events_parsed"


def _event_hubs_stream():
    """Create the verified Kafka source while keeping the SAS key in runtime memory."""
    try:
        from databricks.sdk.runtime import dbutils
    except ImportError as exc:  # pragma: no cover - Databricks runtime boundary
        raise RuntimeError("Databricks dbutils is required for secret lookup") from exc

    namespace = _conf("event_hubs.namespace")
    policy_key = dbutils.secrets.get(
        scope=_conf("event_hubs.secret_scope"),
        key=_conf("event_hubs.secret_key"),
    )
    connection = connection_string(
        namespace,
        _conf("event_hubs.sas_policy_name"),
        policy_key,
    )
    reader = (
        _spark()
        .readStream.format("kafka")
        .option("kafka.bootstrap.servers", f"{namespace}.servicebus.windows.net:9093")
        .option("subscribe", _conf("event_hubs.topic"))
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "PLAIN")
        .option("kafka.sasl.jaas.config", jaas_config(connection))
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "true")
    )
    if not DIRECT_EVENTHUB_FANOUT:
        reader = reader.option(
            "kafka.group.id",
            _conf("event_hubs.consumer_group"),
        )
    return reader.load()


def _bronze_rows_from_event_hubs():
    return generic_bronze_rows(_event_hubs_stream())


def _parsed_gps_from_bronze():
    bronze = _spark().readStream.table(TABLES.bronze_table)
    return parse_bronze_rows(gps_parser_input_rows(bronze))


def _parsed_gps_direct_from_event_hubs():
    return parse_bronze_rows(
        gps_parser_input_rows(_bronze_rows_from_event_hubs())
    )


@dp.table(
    name=TABLES.bronze_table,
    schema=GENERIC_BRONZE_SCHEMA_DDL,
    comment="Raw Event Hubs payloads with minimal routing metadata and provenance.",
)
@dp.expect_or_fail("raw_payload_is_not_null", "raw_payload IS NOT NULL")
def bronze_events():
    return _bronze_rows_from_event_hubs()


if not FUSE_GPS_PARSE_VALIDATION:
    @dp.table(
        name=_GPS_PARSED_TABLE,
        private=True,
        comment="Private parsed and contract-validated GPS events.",
    )
    def gps_events_parsed():
        return _parsed_gps_from_bronze()


@dp.table(
    name=TABLES.observations_table,
    schema=OBSERVATIONS_SCHEMA_DDL,
    comment="Validated GPS observations with optional bounded event_id deduplication.",
)
def gps_observations():
    parsed = (
        _parsed_gps_direct_from_event_hubs()
        if DIRECT_EVENTHUB_FANOUT
        else (
            _parsed_gps_from_bronze()
            if FUSE_GPS_PARSE_VALIDATION
            else _spark().readStream.table(_GPS_PARSED_TABLE)
        )
    )
    observations = valid_observation_rows(parsed)
    if APPLY_DEDUPLICATION:
        return deduplicate_observations(observations, DEDUPLICATION_WATERMARK)
    return observations


@dp.table(
    name=TABLES.quarantine_table,
    schema=QUARANTINE_SCHEMA_DDL,
    comment="Rejected GPS events with validation reasons and raw context.",
)
def gps_quarantine():
    parsed = (
        _parsed_gps_from_bronze()
        if FUSE_GPS_PARSE_VALIDATION
        else _spark().readStream.table(_GPS_PARSED_TABLE)
    )
    return quarantine_rows(parsed)


@dp.table(
    name=TABLES.trip_ended_events_table,
    schema=TRIP_ENDED_SCHEMA_DDL,
    comment="Validated primitive trip_ended events with optional bounded event_id deduplication.",
)
def trip_ended_events():
    source = (
        _bronze_rows_from_event_hubs()
        if DIRECT_EVENTHUB_FANOUT
        else _spark().readStream.table(TABLES.bronze_table)
    )
    events = trip_ended_rows(source)
    if APPLY_DEDUPLICATION:
        return deduplicate_event_ids(events, DEDUPLICATION_WATERMARK)
    return events

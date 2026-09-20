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
    return (
        _spark()
        .readStream.format("kafka")
        .option("kafka.bootstrap.servers", f"{namespace}.servicebus.windows.net:9093")
        .option("subscribe", _conf("event_hubs.topic"))
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "PLAIN")
        .option("kafka.sasl.jaas.config", jaas_config(connection))
        .option("kafka.group.id", _conf("event_hubs.consumer_group"))
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "true")
        .load()
    )


@dp.table(
    name=TABLES.bronze_table,
    schema=GENERIC_BRONZE_SCHEMA_DDL,
    comment="Raw Event Hubs payloads with minimal routing metadata and provenance.",
)
@dp.expect_or_fail("raw_payload_is_not_null", "raw_payload IS NOT NULL")
def bronze_events():
    return generic_bronze_rows(_event_hubs_stream())


@dp.table(
    name=_GPS_PARSED_TABLE,
    private=True,
    comment="Private parsed and contract-validated GPS events.",
)
def gps_events_parsed():
    bronze = _spark().readStream.table(TABLES.bronze_table)
    return parse_bronze_rows(gps_parser_input_rows(bronze))


@dp.table(
    name=TABLES.observations_table,
    schema=OBSERVATIONS_SCHEMA_DDL,
    comment="Validated GPS observations with bounded event_id deduplication.",
)
def gps_observations():
    observations = valid_observation_rows(
        _spark().readStream.table(_GPS_PARSED_TABLE)
    )
    return deduplicate_observations(observations, DEDUPLICATION_WATERMARK)


@dp.table(
    name=TABLES.quarantine_table,
    schema=QUARANTINE_SCHEMA_DDL,
    comment="Rejected GPS events with validation reasons and raw context.",
)
def gps_quarantine():
    return quarantine_rows(_spark().readStream.table(_GPS_PARSED_TABLE))


@dp.table(
    name=TABLES.trip_ended_events_table,
    schema=TRIP_ENDED_SCHEMA_DDL,
    comment="Validated primitive trip_ended events for the finalization layer.",
)
def trip_ended_events():
    events = trip_ended_rows(_spark().readStream.table(TABLES.bronze_table))
    return deduplicate_event_ids(events, DEDUPLICATION_WATERMARK)

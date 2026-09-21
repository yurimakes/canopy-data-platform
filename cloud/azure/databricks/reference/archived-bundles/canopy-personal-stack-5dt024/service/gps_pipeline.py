"""Keep historical Bronze/Silver flows; add a directly validated low-latency view.

The fast table has its own Kafka consumer/checkpoint. It runs the exact same
contract validation and deduplication functions, without two intermediate Delta
commits on the app's critical path. Original tables are retained for audit/retry.
"""
from pyspark import pipelines as dp
from databricks.sdk.runtime import dbutils
from gps_ingestion import lakeflow_pipeline as original
from gps_ingestion.event_hubs_auth import connection_string,jaas_config
from gps_ingestion.spark_ingestion import (
    OBSERVATIONS_SCHEMA_DDL,bronze_rows,parse_bronze_rows,
    valid_observation_rows,deduplicate_observations,
)


def source():
    conf=original._conf
    namespace=conf('event_hubs.namespace')
    key=dbutils.secrets.get(scope=conf('event_hubs.secret_scope'),key=conf('event_hubs.secret_key'))
    connection=connection_string(namespace,conf('event_hubs.sas_policy_name'),key)
    return (original._spark().readStream.format('kafka')
        .option('kafka.bootstrap.servers',f'{namespace}.servicebus.windows.net:9093')
        .option('subscribe',conf('event_hubs.topic'))
        .option('kafka.security.protocol','SASL_SSL')
        .option('kafka.sasl.mechanism','PLAIN')
        .option('kafka.sasl.jaas.config',jaas_config(connection))
        .option('kafka.group.id',conf('event_hubs.fast_consumer_group'))
        .option('startingOffsets','earliest')
        .option('failOnDataLoss','true').load())


@dp.table(
    name=f"{original._conf('catalog')}.{original._conf('silver_schema')}.gps_observations_live",
    schema=OBSERVATIONS_SCHEMA_DDL,
    comment='Same validated GPS contract; direct Kafka fanout for live and final Trip latency.',
    spark_conf={'pipelines.trigger.interval':'1 second'},
)
def gps_observations_live():
    parsed=parse_bronze_rows(bronze_rows(source()))
    return deduplicate_observations(valid_observation_rows(parsed),original.DEDUPLICATION_WATERMARK)

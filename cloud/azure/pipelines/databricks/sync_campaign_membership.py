import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_MEMBERSHIP_CONTAINER = os.environ.get("CANOPY_COSMOS_MEMBERSHIP_CONTAINER", "campaign_memberships")

ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH = os.environ.get(
    "CANOPY_ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/curated/campaign_membership_raw/",
)

KEEP_FIELDS = ["user_id", "campaign_id", "department_id", "joined_at", "left_at"]


def _get_container():
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_MEMBERSHIP_CONTAINER)


def read_memberships_from_cosmos(campaign_id):
    container = _get_container()
    query = "SELECT * FROM c WHERE c.campaign_id = @campaign_id"
    params = [{"name": "@campaign_id", "value": campaign_id}]
    return list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))


def _strip_membership(item):
    return {field: item.get(field) for field in KEEP_FIELDS}


def write_raw(spark, campaign_id, rows):
    schema = "user_id string, campaign_id string, department_id string, joined_at string, left_at string"
    df = spark.createDataFrame(rows, schema=schema) if rows else spark.createDataFrame([], schema=schema)
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id")
        .save(ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH)
    )
    return df


def verify(spark, campaign_id):
    df = spark.read.format("delta").load(ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH)
    count = df.filter(df.campaign_id == campaign_id).count()
    print(f"[verify] campaign_id={campaign_id} campaign_membership_raw rows={count}")
    return count


def run(campaign_id):
    spark = SparkSession.builder.getOrCreate()

    items = read_memberships_from_cosmos(campaign_id)
    rows = [_strip_membership(i) for i in items]
    write_raw(spark, campaign_id, rows)

    count = verify(spark, campaign_id)
    print(f"[done] campaign_id={campaign_id} memberships_synced={len(items)} rows={count}")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if not campaign_id_arg:
        raise ValueError("campaign_id parameter required")

    run(campaign_id_arg)

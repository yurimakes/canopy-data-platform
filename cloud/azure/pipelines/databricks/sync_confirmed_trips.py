import os

from azure.cosmos import CosmosClient
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

def _get_secret_or_env(scope, secret_key, env_var):
    try:
        return dbutils.secrets.get(scope=scope, key=secret_key)  # noqa: F821
    except Exception:
        return os.environ.get(env_var)


COSMOS_ENDPOINT = _get_secret_or_env("canopy-scope", "cosmos-endpoint", "CANOPY_COSMOS_ENDPOINT")
COSMOS_KEY = _get_secret_or_env("canopy-scope", "cosmos-key", "CANOPY_COSMOS_KEY")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_CONTAINER = "trips"

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)


def read_confirmed_from_cosmos():
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    database = client.get_database_client(COSMOS_DATABASE)
    container = database.get_container_client(COSMOS_CONTAINER)

    query = "SELECT * FROM c WHERE c.confirmation_status = 'confirmed'"
    return list(container.query_items(query=query, enable_cross_partition_query=True))


KEEP_FIELDS = [
    "trip_id", "user_id", "campaign_id", "status", "confirmation_status",
    "started_at", "ended_at", "updated_at", "segments", "carbon",
]

SEGMENT_KEEP_FIELDS = ["segment_id", "model_prediction", "distance_m"]
CARBON_KEEP_FIELDS = ["kg_co2e"]


def _strip_segment(segment):
    return {k: segment.get(k) for k in SEGMENT_KEEP_FIELDS}


def _strip_to_known_fields(item):
    trimmed = {k: item.get(k) for k in KEEP_FIELDS}
    if trimmed.get("segments"):
        trimmed["segments"] = [_strip_segment(s) for s in trimmed["segments"]]
    if trimmed.get("carbon"):
        trimmed["carbon"] = {k: trimmed["carbon"].get(k) for k in CARBON_KEEP_FIELDS}
    return trimmed


def write_curated(spark, items):
    if not items:
        raise RuntimeError("no confirmed trips returned from Cosmos DB")

    trimmed = [_strip_to_known_fields(item) for item in items]
    df = spark.createDataFrame(trimmed)

    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id")
        .save(CONFIRMED_TRIPS_PATH)
    )


def verify(spark):
    df = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH)
    count = df.count()
    print(f"[verify] confirmed_trips rows={count}")
    return count > 0


def run():
    spark = SparkSession.builder.getOrCreate()

    items = read_confirmed_from_cosmos()
    write_curated(spark, items)

    ok = verify(spark)
    if not ok:
        raise RuntimeError("confirmed_trips sync failed: empty result")

    print("[done] confirmed_trips sync complete")


if __name__ == "__main__":
    run()

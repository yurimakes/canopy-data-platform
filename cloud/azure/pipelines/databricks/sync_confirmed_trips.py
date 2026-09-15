import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_CONTAINER = os.environ.get("CANOPY_COSMOS_TRIPS_CONTAINER", "trips")

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)


def read_confirmed_from_cosmos():
    """Read finalized system Trip results.

    `confirmation_status` is not treated as a user override gate. The current backend
    finishes automatic processing by setting Trip `status=ready`; user issue feedback
    is a separate support workflow and does not change the baseline input automatically.
    """
    if not COSMOS_ENDPOINT:
        raise RuntimeError("CANOPY_COSMOS_ENDPOINT is required")

    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    database = client.get_database_client(COSMOS_DATABASE)
    container = database.get_container_client(COSMOS_CONTAINER)

    query = "SELECT * FROM c WHERE c.type = 'trip' AND c.status = 'ready'"
    return list(container.query_items(query=query, enable_cross_partition_query=True))


KEEP_FIELDS = [
    "trip_id",
    "user_id",
    "campaign_id",
    "status",
    "confirmation_status",
    "confirmation_source",
    "started_at",
    "ended_at",
    "updated_at",
    "segments",
    "carbon",
]

SEGMENT_KEEP_FIELDS = [
    "segment_id",
    "model_prediction",
    "distance_m",
    "carbon_kg",
]
CARBON_KEEP_FIELDS = [
    "kg_co2e",
    "mode_source",
    "user_confirmation_applied",
    "policy_version",
    "factor_version",
    "unit",
]


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
        raise RuntimeError("no ready trips returned from Cosmos DB")

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
    print(f"[verify] ready baseline-input trips rows={count}")
    return count > 0


def run():
    spark = SparkSession.builder.getOrCreate()

    items = read_confirmed_from_cosmos()
    write_curated(spark, items)

    ok = verify(spark)
    if not ok:
        raise RuntimeError("Trip baseline-input sync failed: empty result")

    print("[done] ready Trip baseline-input sync complete")


if __name__ == "__main__":
    run()

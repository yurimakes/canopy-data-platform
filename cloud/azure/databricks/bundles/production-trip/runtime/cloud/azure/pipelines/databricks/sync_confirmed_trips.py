import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession
from pyspark.sql import Window
from pyspark.sql import functions as F

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_CONTAINER = os.environ.get("CANOPY_COSMOS_TRIPS_CONTAINER", "trips")

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)

KEEP_FIELDS = [
    "schema_version", "trip_id", "user_id", "campaign_id",
    "started_at", "ended_at", "confirmed_at", "revision", "confirmation_status",
    "total_distance_m", "total_carbon_kg",
    "walk_distance_m", "bike_distance_m", "car_distance_m", "bus_distance_m", "rail_distance_m",
    "carbon_unit", "carbon_policy_version", "factor_version",
    "mode_source", "confirmation_source", "is_mock", "model_version",
]

SCHEMA = (
    "schema_version string, trip_id string, user_id string, campaign_id string, "
    "started_at string, ended_at string, confirmed_at string, revision int, confirmation_status string, "
    "total_distance_m double, total_carbon_kg double, "
    "walk_distance_m double, bike_distance_m double, car_distance_m double, "
    "bus_distance_m double, rail_distance_m double, "
    "carbon_unit string, carbon_policy_version string, factor_version string, "
    "mode_source string, confirmation_source string, is_mock boolean, model_version string"
)


def read_confirmed_from_cosmos():
    """Read the confirmed_trip sub-document from finalized Trips.

    confirmed_trip is a pre-aggregated per-trip summary (already split by mode,
    already totaled for carbon) written once a Trip's automatic processing
    completes. Trips without a confirmed_trip sub-document yet are skipped.
    """
    if not COSMOS_ENDPOINT:
        raise RuntimeError("CANOPY_COSMOS_ENDPOINT is required")

    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    database = client.get_database_client(COSMOS_DATABASE)
    container = database.get_container_client(COSMOS_CONTAINER)

    query = "SELECT * FROM c WHERE c.type = 'trip' AND c.status = 'ready'"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))

    confirmed = [item.get("confirmed_trip") for item in items]
    return [c for c in confirmed if c is not None]


def _strip_to_known_fields(confirmed_trip):
    return {k: confirmed_trip.get(k) for k in KEEP_FIELDS}


def dedupe_latest_revision(df):
    """Keep only the highest revision per trip_id; corrections replace, never append."""
    w = Window.partitionBy("trip_id").orderBy(F.col("revision").desc())
    ranked = df.withColumn("_rn", F.row_number().over(w))
    return ranked.filter(F.col("_rn") == 1).drop("_rn")


def write_curated(spark, rows):
    if not rows:
        raise RuntimeError("no confirmed_trip sub-documents found")

    trimmed = [_strip_to_known_fields(r) for r in rows]
    df = spark.createDataFrame(trimmed, schema=SCHEMA)
    df = df.filter(F.col("is_mock") == False)  # noqa: E712
    df = dedupe_latest_revision(df)

    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id")
        .save(CONFIRMED_TRIPS_PATH)
    )
    return df


def verify(spark):
    df = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH)
    count = df.count()
    print(f"[verify] confirmed_trips rows={count}")
    return count > 0


def run():
    spark = SparkSession.builder.getOrCreate()

    rows = read_confirmed_from_cosmos()
    write_curated(spark, rows)

    ok = verify(spark)
    if not ok:
        raise RuntimeError("confirmed_trips sync failed: empty result")

    print("[done] confirmed_trips sync complete")


if __name__ == "__main__":
    run()
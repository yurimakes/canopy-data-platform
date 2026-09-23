import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_MISSION_CONTAINER = os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")

ADLS_MISSION_BUNDLES_RAW_PATH = os.environ.get(
    "CANOPY_ADLS_MISSION_BUNDLES_RAW_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/curated/mission_bundles_raw/",
)

BUNDLE_FIELDS = [
    "campaign_id", "user_id", "week_start", "week_end", "bundle_id",
    "common_target_count", "policy_version",
]
MISSION_FIELDS = [
    "assignment_id", "category_id", "mission_template_id", "mission_family",
    "difficulty_band", "target_count", "progress_count", "achievement_rate", "completed",
    "affinity_comparable", "difficulty_comparable", "preference_comparable",
]


def _get_container():
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_MISSION_CONTAINER)


def read_bundles_from_cosmos(campaign_id, week_start):
    container = _get_container()
    query = (
        "SELECT * FROM c WHERE c.campaign_id = @campaign_id "
        "AND c.week_start = @week_start AND c.type = 'mission_bundle'"
    )
    params = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@week_start", "value": week_start},
    ]
    return list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))


def _strip_bundle(bundle):
    row = {field: bundle.get(field) for field in BUNDLE_FIELDS}
    missions = []
    for mission in bundle.get("missions") or []:
        m = {field: mission.get(field) for field in MISSION_FIELDS}
        missions.append(m)
    row["missions"] = missions
    return row


def write_raw(spark, rows):
    schema = (
        "campaign_id string, user_id string, week_start string, week_end string, "
        "bundle_id string, common_target_count long, policy_version string, "
        "missions array<struct<"
        "assignment_id:string, category_id:string, mission_template_id:string, mission_family:string, "
        "difficulty_band:string, target_count:long, progress_count:long, achievement_rate:double, "
        "completed:boolean, affinity_comparable:boolean, difficulty_comparable:boolean, "
        "preference_comparable:boolean>>"
    )
    df = spark.createDataFrame(rows, schema=schema) if rows else spark.createDataFrame([], schema=schema)
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week_start")
        .save(ADLS_MISSION_BUNDLES_RAW_PATH)
    )
    return df


def verify(spark, campaign_id, week_start):
    df = spark.read.format("delta").load(ADLS_MISSION_BUNDLES_RAW_PATH)
    count = df.filter((df.campaign_id == campaign_id) & (df.week_start == week_start)).count()
    print(f"[verify] campaign_id={campaign_id} week_start={week_start} mission_bundles_raw rows={count}")
    return count


def run(campaign_id, week_start):
    spark = SparkSession.builder.getOrCreate()

    bundles = read_bundles_from_cosmos(campaign_id, week_start)
    rows = [_strip_bundle(b) for b in bundles]
    write_raw(spark, rows)

    count = verify(spark, campaign_id, week_start)
    print(f"[done] campaign_id={campaign_id} week_start={week_start} bundles_synced={len(bundles)} rows={count}")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_start_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if not (campaign_id_arg and week_start_arg):
        raise ValueError("campaign_id and week_start (YYYY-MM-DD) parameters required")

    run(campaign_id_arg, week_start_arg)

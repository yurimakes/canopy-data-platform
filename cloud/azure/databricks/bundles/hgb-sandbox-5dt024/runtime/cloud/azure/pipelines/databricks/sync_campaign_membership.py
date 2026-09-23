import os
from datetime import datetime

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")
COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_USERS_CONTAINER = os.environ.get("CANOPY_USERS_CONTAINER", "users")

ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH = os.environ.get(
    "CANOPY_ADLS_CAMPAIGN_MEMBERSHIP_RAW_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/curated/campaign_membership_raw/",
)

KEEP_FIELDS = ["user_id", "campaign_id", "department_id", "joined_at", "left_at"]


def _get_container(endpoint=None, secret_scope=None, secret_key=None):
    endpoint = endpoint or COSMOS_ENDPOINT
    if not endpoint:
        raise ValueError("Cosmos endpoint required")
    if bool(secret_scope) != bool(secret_key):
        raise ValueError("Both secret scope and key required")
    if secret_scope:
        from databricks.sdk.runtime import dbutils
        credential = dbutils.secrets.get(scope=secret_scope, key=secret_key)
    else:
        credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(COSMOS_USERS_CONTAINER)


def read_memberships_from_cosmos(campaign_id, **connection):
    container = _get_container(**connection)
    query = "SELECT * FROM c WHERE c.campaign_id = @campaign_id"
    params = [{"name": "@campaign_id", "value": campaign_id}]
    return list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))


def _strip_membership(item):
    # 가입 시 확정한 참여일을 기존 ADLS joined_at 열로 전달. 첫 Trip 기준 변경 제외.
    for key in ("user_id", "campaign_id", "created_at", "campaign_joined_at"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError("users participation field missing: " + key)
    joined = datetime.fromisoformat(item["campaign_joined_at"].replace("Z", "+00:00"))
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if joined.tzinfo is None or created.tzinfo is None:
        raise ValueError("Registration timestamps require timezone")
    if joined != created:
        raise ValueError("campaign_joined_at must equal created_at under signup participation policy")
    return {
        "user_id": item["user_id"], "campaign_id": item["campaign_id"],
        "department_id": item.get("department_id"),
        "joined_at": item["campaign_joined_at"], "left_at": item.get("campaign_left_at"),
    }


def write_raw(spark, campaign_id, rows):
    schema = "user_id string, campaign_id string, department_id string, joined_at string, left_at string"
    df = spark.createDataFrame(rows, schema=schema) if rows else spark.createDataFrame([], schema=schema)
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", "campaign_id = '" + campaign_id.replace("'", "''") + "'")
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


def run(campaign_id, **connection):
    if not campaign_id or "{{" in campaign_id:
        raise ValueError("Resolved campaign_id required")
    spark = SparkSession.builder.getOrCreate()

    items = read_memberships_from_cosmos(campaign_id, **connection)
    rows = [_strip_membership(i) for i in items]
    write_raw(spark, campaign_id, rows)

    count = verify(spark, campaign_id)
    print(f"[done] campaign_id={campaign_id} memberships_synced={len(items)} rows={count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_id")
    parser.add_argument("--endpoint")
    parser.add_argument("--secret-scope")
    parser.add_argument("--secret-key")
    args = parser.parse_args()
    run(args.campaign_id, endpoint=args.endpoint, secret_scope=args.secret_scope, secret_key=args.secret_key)

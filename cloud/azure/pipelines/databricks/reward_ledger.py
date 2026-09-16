import os
import uuid
from datetime import datetime, timezone

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError

COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_REWARD_LEDGER_CONTAINER = os.environ.get("CANOPY_COSMOS_REWARD_LEDGER_CONTAINER", "rewards")
GOLD_REWARD_LEDGER_HISTORY_PATH = os.environ.get(
    "CANOPY_GOLD_REWARD_LEDGER_HISTORY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/reward_ledger_history/",
)


def _get_secret_or_env(scope, secret_key, env_var):
    try:
        return dbutils.secrets.get(scope=scope, key=secret_key)  # noqa: F821
    except Exception:
        return os.environ.get(env_var)


COSMOS_ENDPOINT = _get_secret_or_env("canopy-scope", "cosmos-endpoint", "CANOPY_COSMOS_ENDPOINT")
COSMOS_KEY = _get_secret_or_env("canopy-scope", "cosmos-key", "CANOPY_COSMOS_KEY")


def _get_container():
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    database = client.get_database_client(COSMOS_DATABASE)
    return database.get_container_client(COSMOS_REWARD_LEDGER_CONTAINER)


def make_reward_id(user_id, campaign_id, week):
    return f"{user_id}_{campaign_id}_{week}"


def write_reward(container, result_row):
    if not result_row.get("payable"):
        return {"status": "skipped", "reason": "not_payable"}

    reward_id = make_reward_id(result_row["user_id"], result_row["campaign_id"], result_row["week"])

    item = {
        "id": reward_id,
        "reward_id": reward_id,
        "user_id": result_row["user_id"],
        "campaign_id": result_row["campaign_id"],
        "week": result_row["week"],
        "points": result_row["points"],
        "reason": result_row["reason"],
        "policy_version": result_row["policy_version"],
        "status": "paid",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        container.create_item(item)
        return {"status": "created", "reward_id": reward_id, "record": item}
    except CosmosResourceExistsError:
        existing = container.read_item(item=reward_id, partition_key=result_row["user_id"])
        return {"status": "already_exists", "reward_id": reward_id, "record": existing}


def process_reward_batch(container, result_rows):
    return [write_reward(container, row) for row in result_rows]


def create_adjustment(container, original_reward_id, user_id, campaign_id, week, points_delta, reason, policy_version):
    adjustment_id = f"adjustment_{original_reward_id}_{uuid.uuid4().hex[:8]}"

    item = {
        "id": adjustment_id,
        "reward_id": adjustment_id,
        "adjusts_reward_id": original_reward_id,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week": week,
        "points": points_delta,
        "reason": reason,
        "policy_version": policy_version,
        "status": "adjustment",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    container.create_item(item)
    return item


def write_ledger_history(spark, outcomes):
    records = [o["record"] for o in outcomes if o["status"] in ("created", "already_exists")]
    if not records:
        return 0

    schema = (
        "id string, reward_id string, user_id string, campaign_id string, week string, "
        "points double, reason string, policy_version string, status string, created_at string"
    )
    df = spark.createDataFrame(records, schema=schema)

    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(GOLD_REWARD_LEDGER_HISTORY_PATH)
    )
    return len(records)


def run(campaign_id, week, reward_calc_path):
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = SparkSession.builder.getOrCreate()
    df = (
        spark.read.format("delta").load(reward_calc_path)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
    )

    result_rows = [row.asDict() for row in df.collect()]
    container = _get_container()
    outcomes = process_reward_batch(container, result_rows)

    history_count = write_ledger_history(spark, outcomes)

    created = sum(1 for o in outcomes if o["status"] == "created")
    existed = sum(1 for o in outcomes if o["status"] == "already_exists")
    skipped = sum(1 for o in outcomes if o["status"] == "skipped")
    print(f"[done] campaign_id={campaign_id} week={week} created={created} already_exists={existed} skipped={skipped} history_rows={history_count}")

    return outcomes


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None
    reward_calc_path_arg = os.environ.get(
        "CANOPY_GOLD_REWARD_CALC_PATH",
        "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/reward_calculation/",
    )

    if not (campaign_id_arg and week_arg):
        raise ValueError("campaign_id and week parameters required")

    run(campaign_id_arg, week_arg, reward_calc_path_arg)

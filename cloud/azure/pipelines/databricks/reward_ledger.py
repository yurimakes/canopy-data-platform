import json
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
REWARD_NAMESPACE = uuid.UUID("013598d6-33a5-49f8-9f1a-ae8b2fc52e82")


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


def make_reward_id(user_id, campaign_id, source_id, reward_type="trip_carbon"):
    """One base reward per source action.

    For trip_carbon, source_id is trip_id. Policy changes do not create a second base
    reward for the same Trip; corrections must use an adjustment record.
    """
    raw = json.dumps([campaign_id, user_id, reward_type, source_id], ensure_ascii=False, separators=(",", ":"))
    return "reward_" + str(uuid.uuid5(REWARD_NAMESPACE, raw))


def write_reward(container, result_row):
    if not result_row.get("payable"):
        return {"status": "skipped", "reason": "not_payable"}

    reward_type = result_row.get("reward_type") or "trip_carbon"
    source_id = result_row.get("trip_id") or result_row.get("assignment_id")
    if not source_id:
        raise ValueError("payable reward requires trip_id or assignment_id as source_id")
    reward_id = make_reward_id(result_row["user_id"], result_row["campaign_id"], source_id, reward_type)

    item = {
        "id": reward_id,
        "reward_id": reward_id,
        "reward_type": reward_type,
        "source_id": source_id,
        "trip_id": result_row.get("trip_id"),
        "assignment_id": result_row.get("assignment_id"),
        "user_id": result_row["user_id"],
        "campaign_id": result_row["campaign_id"],
        "week": result_row["week"],
        "points": result_row["points"],
        "reason": result_row["reason"],
        "status": "paid",
        "baseline_source": result_row.get("baseline_source"),
        "selected_baseline_g_co2e_per_km": result_row.get("selected_baseline_g_co2e_per_km"),
        "actual_g_co2e_per_km": result_row.get("actual_g_co2e_per_km"),
        "policy_version": result_row["policy_version"],
        "baseline_policy_version": result_row.get("baseline_policy_version"),
        "eligibility_policy_version": result_row.get("eligibility_policy_version"),
        "carbon_policy_version": result_row.get("carbon_policy_version"),
        "factor_version": result_row.get("factor_version"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        container.create_item(item)
        return {"status": "created", "reward_id": reward_id, "record": item}
    except CosmosResourceExistsError:
        # Current rewards container contract uses user_id as the partition value.
        existing = container.read_item(item=reward_id, partition_key=result_row["user_id"])
        return {"status": "already_exists", "reward_id": reward_id, "record": existing}


def process_reward_batch(container, result_rows):
    return [write_reward(container, row) for row in result_rows]


def create_adjustment(container, original_reward_id, user_id, campaign_id, week, points_delta, reason, policy_version):
    adjustment_id = f"adjustment_{original_reward_id}_{uuid.uuid4().hex[:8]}"
    item = {
        "id": adjustment_id,
        "reward_id": adjustment_id,
        "reward_type": "adjustment",
        "adjusts_reward_id": original_reward_id,
        "source_id": original_reward_id,
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

    # Explicitly select the stable audit contract. Additional Cosmos fields can be added
    # later without making the Delta history consumer depend on document inference.
    normalized = [{
        "id": r.get("id"),
        "reward_id": r.get("reward_id"),
        "reward_type": r.get("reward_type"),
        "source_id": r.get("source_id"),
        "trip_id": r.get("trip_id"),
        "assignment_id": r.get("assignment_id"),
        "user_id": r.get("user_id"),
        "campaign_id": r.get("campaign_id"),
        "week": r.get("week"),
        "points": r.get("points"),
        "reason": r.get("reason"),
        "baseline_source": r.get("baseline_source"),
        "selected_baseline_g_co2e_per_km": r.get("selected_baseline_g_co2e_per_km"),
        "actual_g_co2e_per_km": r.get("actual_g_co2e_per_km"),
        "policy_version": r.get("policy_version"),
        "baseline_policy_version": r.get("baseline_policy_version"),
        "eligibility_policy_version": r.get("eligibility_policy_version"),
        "carbon_policy_version": r.get("carbon_policy_version"),
        "factor_version": r.get("factor_version"),
        "status": r.get("status"),
        "created_at": r.get("created_at"),
    } for r in records]

    schema = (
        "id string, reward_id string, reward_type string, source_id string, trip_id string, assignment_id string, "
        "user_id string, campaign_id string, week string, points double, reason string, baseline_source string, "
        "selected_baseline_g_co2e_per_km double, actual_g_co2e_per_km double, policy_version string, "
        "baseline_policy_version string, eligibility_policy_version string, carbon_policy_version string, "
        "factor_version string, status string, created_at string"
    )
    df = spark.createDataFrame(normalized, schema=schema)
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
    result_rows = [row.asDict(recursive=True) for row in df.collect()]
    container = _get_container()
    outcomes = process_reward_batch(container, result_rows)
    history_count = write_ledger_history(spark, outcomes)

    created = sum(1 for o in outcomes if o["status"] == "created")
    existed = sum(1 for o in outcomes if o["status"] == "already_exists")
    skipped = sum(1 for o in outcomes if o["status"] == "skipped")
    print(
        f"[done] campaign_id={campaign_id} week={week} created={created} "
        f"already_exists={existed} skipped={skipped} history_rows={history_count}"
    )
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

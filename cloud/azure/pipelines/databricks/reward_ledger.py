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

LEDGER_HISTORY_SCHEMA = (
    "id string, reward_id string, adjusts_reward_id string, user_id string, "
    "campaign_id string, week string, week_label string, label string, "
    "points double, status string, occurred_at string, policy_version string"
)
LEDGER_HISTORY_STATUSES = ("paid", "adjusted")


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


def _week_label_to_start_date(week_label):
    year, week = week_label.split("-W")
    return datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date().isoformat()


def write_reward(container, result_row):
    if not result_row.get("payable"):
        return {"status": "skipped", "reason": "not_payable"}

    reward_id = make_reward_id(result_row["user_id"], result_row["campaign_id"], result_row["week"])
    week_start = _week_label_to_start_date(result_row["week"])

    item = {
        "id": reward_id,
        "reward_id": reward_id,
        "user_id": result_row["user_id"],
        "campaign_id": result_row["campaign_id"],
        "week": week_start,
        "week_label": result_row["week"],
        "label": result_row["reason"],
        "points": result_row["points"],
        "status": "paid",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": result_row["policy_version"],
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
    week_start = _week_label_to_start_date(week)

    item = {
        "id": adjustment_id,
        "reward_id": adjustment_id,
        "adjusts_reward_id": original_reward_id,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week": week_start,
        "week_label": week,
        "label": reason,
        "points": points_delta,
        "status": "adjusted",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": policy_version,
    }

    container.create_item(item)
    return item


def _ledger_history_frame(spark, records):
    if records:
        return spark.createDataFrame(records, schema=LEDGER_HISTORY_SCHEMA)
    return spark.createDataFrame([], schema=LEDGER_HISTORY_SCHEMA)


def write_ledger_history(spark, outcomes):
    """Upsert paid reward outcomes without deleting existing adjustments."""
    records = [o["record"] for o in outcomes if o["status"] in ("created", "already_exists")]
    if not records:
        return 0

    from delta.tables import DeltaTable

    df = _ledger_history_frame(spark, records)
    if DeltaTable.isDeltaTable(spark, GOLD_REWARD_LEDGER_HISTORY_PATH):
        (
            DeltaTable.forPath(spark, GOLD_REWARD_LEDGER_HISTORY_PATH)
            .alias("target")
            .merge(df.alias("source"), "target.reward_id = source.reward_id")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        (
            df.write.format("delta")
            .mode("overwrite")
            .partitionBy("campaign_id", "week_label")
            .save(GOLD_REWARD_LEDGER_HISTORY_PATH)
        )
    return len(records)


def read_ledger_partition(container, campaign_id, week):
    """Read the authoritative paid/adjusted Reward Ledger partition from Cosmos."""
    query = """
        SELECT c.id, c.reward_id, c.adjusts_reward_id, c.user_id,
               c.campaign_id, c.week, c.week_label, c.label, c.points,
               c.status, c.occurred_at, c.policy_version
        FROM c
        WHERE c.campaign_id = @campaign_id
          AND c.week_label = @week_label
          AND (c.status = "paid" OR c.status = "adjusted")
    """
    parameters = [
        {"name": "@campaign_id", "value": campaign_id},
        {"name": "@week_label", "value": week},
    ]
    records = list(
        container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
    )

    normalized = []
    for item in records:
        reward_id = item.get("reward_id") or item.get("id")
        if not reward_id:
            raise ValueError("Reward Ledger row missing reward_id")
        if item.get("campaign_id") != campaign_id or item.get("week_label") != week:
            raise ValueError("Reward Ledger row outside requested campaign/week")
        if item.get("status") not in LEDGER_HISTORY_STATUSES:
            raise ValueError("Reward Ledger row has unsupported status")
        normalized.append(
            {
                "id": item.get("id") or reward_id,
                "reward_id": reward_id,
                "adjusts_reward_id": item.get("adjusts_reward_id"),
                "user_id": item.get("user_id"),
                "campaign_id": item.get("campaign_id"),
                "week": item.get("week"),
                "week_label": item.get("week_label"),
                "label": item.get("label"),
                "points": item.get("points"),
                "status": item.get("status"),
                "occurred_at": item.get("occurred_at"),
                "policy_version": item.get("policy_version"),
            }
        )
    return normalized


def write_ledger_partition(spark, campaign_id, week, records):
    """Idempotently replace one campaign/week Gold partition from the ledger source."""
    from delta.tables import DeltaTable

    for record in records:
        if record.get("campaign_id") != campaign_id or record.get("week_label") != week:
            raise ValueError("Reward Ledger history write contains a foreign partition")

    df = _ledger_history_frame(spark, records)
    predicate = (
        "campaign_id = '" + campaign_id.replace("'", "''")
        + "' AND week_label = '" + week.replace("'", "''") + "'"
    )

    writer = (
        df.write.format("delta")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week_label")
    )
    if DeltaTable.isDeltaTable(spark, GOLD_REWARD_LEDGER_HISTORY_PATH):
        writer.mode("overwrite").option("replaceWhere", predicate).save(
            GOLD_REWARD_LEDGER_HISTORY_PATH
        )
    else:
        writer.mode("overwrite").save(GOLD_REWARD_LEDGER_HISTORY_PATH)
    return len(records)


def sync_ledger_history_from_cosmos(spark, container, campaign_id, week):
    records = read_ledger_partition(container, campaign_id, week)
    return write_ledger_partition(spark, campaign_id, week, records)


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

    history_count = sync_ledger_history_from_cosmos(
        spark,
        container,
        campaign_id,
        week,
    )

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

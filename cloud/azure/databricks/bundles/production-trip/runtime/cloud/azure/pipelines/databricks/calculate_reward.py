import os

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

REWARD_POLICY_PATH = os.environ.get(
    "CANOPY_REWARD_POLICY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/reward_policy.yaml",
)
GOLD_REWARD_CALC_PATH = os.environ.get(
    "CANOPY_GOLD_REWARD_CALC_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/reward_calculation/",
)


def load_policy(path):
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_reward_status(personal_baseline, global_baseline, actual):
    if personal_baseline is None and global_baseline is None:
        return "not_eligible", "no personal or global baseline available"

    if personal_baseline is not None and (personal_baseline - actual) > 0:
        return "improved", f"personal_baseline({personal_baseline}) - actual({actual}) > 0"

    if global_baseline is not None and actual <= global_baseline:
        return "maintained", f"actual({actual}) <= global_baseline({global_baseline})"

    return "no_change", "no improvement over personal_baseline and not below global_baseline"


def compute_points(status, personal_baseline, global_baseline, actual, policy):
    if status == "not_eligible":
        return None, "not_eligible"

    if status == "no_change":
        points = policy.get("points", {}).get("no_change")
        return points, "policy.points.no_change"

    conversion_rate = policy.get("point_formula", {}).get("conversion_rate")
    if conversion_rate is None:
        return None, "point_formula.conversion_rate not configured in policy"

    if status == "improved":
        delta = personal_baseline - actual
    else:
        delta = global_baseline - actual

    points = max(delta, 0) / conversion_rate
    return points, f"max(delta={delta}, 0) / conversion_rate({conversion_rate})"


def read_current_performance(spark, campaign_id, week):
    df = (
        spark.read.table("weekly_gold")
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
        .withColumn(
            "actual_g_co2e_per_km",
            F.when(
                F.col("total_distance_m") > 0,
                (F.col("total_kg_co2e") * 1000.0) / (F.col("total_distance_m") / 1000.0),
            ),
        )
        .select("user_id", "actual_g_co2e_per_km")
    )
    return {r["user_id"]: r["actual_g_co2e_per_km"] for r in df.collect()}


def read_personal_baseline_map(spark, campaign_id, week):
    df = (
        spark.read.table("personal_baseline")
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week) & (F.col("status") == "ready"))
        .select("user_id", "value")
    )
    return {r["user_id"]: r["value"] for r in df.collect()}


def read_global_baseline_value(spark, campaign_id, week):
    df = (
        spark.read.table("global_baseline")
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week) & (F.col("status") == "ready"))
        .select("value")
    )
    row = df.first()
    return row["value"] if row else None


def read_mission_completion(spark, campaign_id, week):
    df = (
        spark.read.table("mission_response_weekly")
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
        .groupBy("user_id")
        .agg(F.sum(F.when(F.col("completed") == True, 1).otherwise(0)).alias("completed_count"))  # noqa: E712
    )
    return {r["user_id"]: r["completed_count"] for r in df.collect()}


def calculate_rewards(spark, campaign_id, week, policy):
    current = read_current_performance(spark, campaign_id, week)
    personal = read_personal_baseline_map(spark, campaign_id, week)
    global_baseline = read_global_baseline_value(spark, campaign_id, week)
    mission = read_mission_completion(spark, campaign_id, week)

    all_user_ids = set(current) | set(personal)

    result_rows = []
    for user_id in all_user_ids:
        actual = current.get(user_id)
        personal_baseline = personal.get(user_id)

        status, reason = classify_reward_status(personal_baseline, global_baseline, actual)
        points, point_reason = compute_points(status, personal_baseline, global_baseline, actual, policy)

        result_rows.append({
            "user_id": user_id,
            "campaign_id": campaign_id,
            "week": week,
            "status": status,
            "payable": status != "not_eligible" and points is not None,
            "points": points,
            "reason": reason,
            "point_reason": point_reason,
            "missions_completed_this_week": mission.get(user_id, 0),
            "policy_version": policy["policy_version"],
        })

    return result_rows


def submit_to_reward_ledger(spark, result_rows):
    schema = (
        "user_id string, campaign_id string, week string, status string, payable boolean, "
        "points double, reason string, point_reason string, missions_completed_this_week long, "
        "policy_version string"
    )
    if not result_rows:
        reward_df = spark.createDataFrame([], schema)
    else:
        reward_df = spark.createDataFrame(result_rows)

    (
        reward_df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(GOLD_REWARD_CALC_PATH)
    )
    return reward_df


def verify(spark, campaign_id, week):
    df = spark.read.format("delta").load(GOLD_REWARD_CALC_PATH)
    count = df.filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week)).count()
    print(f"[verify] campaign_id={campaign_id} week={week} reward_calc rows={count}")
    return count > 0


def run(campaign_id, week):
    spark = SparkSession.builder.getOrCreate()
    policy = load_policy(REWARD_POLICY_PATH)

    result_rows = calculate_rewards(spark, campaign_id, week, policy)
    submit_to_reward_ledger(spark, result_rows)

    ok = verify(spark, campaign_id, week)
    if not ok:
        raise RuntimeError(f"campaign_id={campaign_id} week={week}: reward calculation verification failed")

    print(f"[done] campaign_id={campaign_id} week={week} reward calculation complete (policy_version={policy['policy_version']})")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if not (campaign_id_arg and week_arg):
        raise ValueError("campaign_id and week parameters required")

    run(campaign_id_arg, week_arg)

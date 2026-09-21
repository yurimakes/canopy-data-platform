import os
from datetime import datetime, timedelta, timezone

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from baseline_eligibility import evaluate_global_eligibility, load_eligibility_policy

GOLD_PERSONAL_BASELINE_PATH = os.environ.get(
    "CANOPY_GOLD_PERSONAL_BASELINE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/personal_baseline_history/",
)
GOLD_GLOBAL_BASELINE_PATH = os.environ.get(
    "CANOPY_GOLD_GLOBAL_BASELINE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/global_baseline_history/",
)

BASELINE_POLICY_PATH = os.environ.get(
    "CANOPY_BASELINE_POLICY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/baseline_policy.yaml",
)


def compute_last_iso_week_label(reference_date=None):
    ref = reference_date or datetime.now(timezone.utc).date()
    this_monday = ref - timedelta(days=ref.weekday())
    week_start = this_monday - timedelta(days=7)
    iso_year, iso_week, _ = week_start.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def load_policy(path):
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_personal_baseline_for_week(spark, campaign_id, evaluation_week):
    df = spark.read.format("delta").load(GOLD_PERSONAL_BASELINE_PATH)
    return df.filter(
        (F.col("campaign_id") == campaign_id) & (F.col("week") == evaluation_week)
    )


def compute_global_baseline(personal_baseline_df, campaign_id, evaluation_week, policy_version,
                            eligibility_policy=None):
    eligibility_policy = eligibility_policy or load_eligibility_policy()
    scoped = personal_baseline_df.filter(
        (F.col("campaign_id") == campaign_id) & (F.col("week") == evaluation_week))
    # Legacy snapshots without eligibility metadata must be reevaluated first.
    if not {"status", "eligibility_policy_version"}.issubset(scoped.columns):
        valid = scoped.limit(0)
    else:
        valid = scoped.filter(
            (F.col("status") == eligibility_policy["global"]["participant_rule"]["require_personal_status"])
            & (F.col("eligibility_policy_version") == eligibility_policy["policy_version"])
            & (F.col("method") == "personal_cumulative")
            & F.col("user_id").isNotNull() & (F.length(F.trim(F.col("user_id"))) > 0)
            & F.col("baseline_g_co2e_per_km").isNotNull()
            & ~F.isnan("baseline_g_co2e_per_km")
            & (F.col("baseline_g_co2e_per_km") >= 0)
            & (F.col("baseline_g_co2e_per_km") < float("inf")))
    if valid.groupBy("user_id").count().filter(F.col("count") > 1).limit(1).count():
        raise ValueError("Duplicate Personal snapshot for user/campaign/week")
    gate = evaluate_global_eligibility(valid.count(), eligibility_policy)
    if gate["status"] == eligibility_policy["global"]["status"]["below_minimum_participants"]:
        return personal_baseline_df.sparkSession.range(1).select(
            F.lit(campaign_id).alias("campaign_id"), F.lit(evaluation_week).alias("week"),
            F.lit(gate["eligible_participant_count"]).cast("long").alias("valid_participant_count"),
            F.lit(None).cast("double").alias("baseline_g_co2e_per_km"),
            F.lit("insufficient_data").alias("method"), F.lit(policy_version).alias("policy_version"),
            F.lit(gate["status"]).alias("status"), F.lit(None).cast("double").alias("value"),
            F.lit(gate["eligible_participant_count"]).cast("long").alias("eligible_participant_count"),
            F.lit(gate["policy_version"]).alias("eligibility_policy_version"))
    # Invoke the original equal-Personal mean only after the gate succeeds.
    return (_compute_global_baseline(valid, campaign_id, evaluation_week, policy_version)
            .withColumn("status", F.lit(gate["status"]))
            .withColumn("value", F.col("baseline_g_co2e_per_km"))
            .withColumn("eligible_participant_count", F.col("valid_participant_count"))
            .withColumn("eligibility_policy_version", F.lit(gate["policy_version"])))


def _compute_global_baseline(personal_baseline_df, campaign_id, evaluation_week, policy_version):
    valid = personal_baseline_df.filter(
        (F.col("method") == "personal_cumulative") & F.col("baseline_g_co2e_per_km").isNotNull()
    )

    agg = valid.agg(
        F.count("user_id").alias("valid_participant_count"),
        F.sum("baseline_g_co2e_per_km").alias("sum_baseline_g_co2e_per_km"),
    )

    return (
        agg
        .withColumn(
            "baseline_g_co2e_per_km",
            F.when(
                F.col("valid_participant_count") > 0,
                F.col("sum_baseline_g_co2e_per_km") / F.col("valid_participant_count"),
            ),
        )
        .withColumn(
            "method",
            F.when(F.col("valid_participant_count") > 0, F.lit("global_average_of_personal_baseline"))
            .otherwise(F.lit("insufficient_data")),
        )
        .withColumn("campaign_id", F.lit(campaign_id))
        .withColumn("week", F.lit(evaluation_week))
        .withColumn("policy_version", F.lit(policy_version))
        .drop("sum_baseline_g_co2e_per_km")
    )


def write_gold(df, path):
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("mergeSchema", "true")
        .option("partitionOverwriteMode", "dynamic")
        .partitionBy("campaign_id")
        .save(path)
    )


def verify(spark, campaign_id):
    df = spark.read.format("delta").load(GOLD_GLOBAL_BASELINE_PATH)
    count = df.filter(F.col("campaign_id") == campaign_id).count()
    print(f"[verify] campaign_id={campaign_id} global_baseline rows={count}")
    return count > 0


def run(campaign_id, evaluation_week):
    spark = SparkSession.builder.getOrCreate()
    policy = load_policy(BASELINE_POLICY_PATH)

    personal_baseline = read_personal_baseline_for_week(spark, campaign_id, evaluation_week)
    global_baseline = compute_global_baseline(personal_baseline, campaign_id, evaluation_week, policy["policy_version"])

    write_gold(global_baseline, GOLD_GLOBAL_BASELINE_PATH)

    ok = verify(spark, campaign_id)
    if not ok:
        raise RuntimeError(f"campaign_id={campaign_id}: global_baseline verification failed")

    print(f"[done] campaign_id={campaign_id} week={evaluation_week} global_baseline complete (policy_version={policy['policy_version']})")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    evaluation_week_arg = sys.argv[2] if len(sys.argv) > 2 else ""

    if not campaign_id_arg:
        raise ValueError("campaign_id parameter required")

    if not evaluation_week_arg:
        evaluation_week_arg = compute_last_iso_week_label()

    run(campaign_id_arg, evaluation_week_arg)

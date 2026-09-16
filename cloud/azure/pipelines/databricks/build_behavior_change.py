from __future__ import annotations

import os

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

GOLD_WEEKLY_USER_PATH = os.environ.get(
    "CANOPY_GOLD_WEEKLY_USER_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/",
)
GOLD_PERSONAL_BASELINE_PATH = os.environ.get(
    "CANOPY_GOLD_PERSONAL_BASELINE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/personal_baseline_history/",
)
GOLD_BEHAVIOR_CHANGE_PATH = os.environ.get(
    "CANOPY_GOLD_BEHAVIOR_CHANGE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/behavior_change_weekly/",
)
BEHAVIOR_CHANGE_POLICY_PATH = os.environ.get(
    "CANOPY_BEHAVIOR_CHANGE_POLICY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/behavior_change_policy.yaml",
)


def load_policy(path: str) -> dict:
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_behavior_change(weekly_user_df, personal_baseline_df, policy: dict):
    """Build one mission-independent Behavior Change row per user/campaign/week.

    The current weekly carbon intensity comes from Weekly User Gold. The reference is
    the Personal Baseline snapshot for the same evaluation week, which itself uses only
    prior completed weeks. Mission bundle/progress/response data are intentionally absent.
    """
    personal = personal_baseline_df.select(
        "user_id",
        "campaign_id",
        "week",
        F.col("status").alias("personal_status"),
        F.col("method").alias("personal_method"),
        F.col("value").cast("double").alias("reference_personal_baseline_g_co2e_per_km"),
        F.col("policy_version").alias("baseline_policy_version"),
        F.col("eligibility_policy_version").alias("eligibility_policy_version"),
    )

    joined = (
        weekly_user_df.select(
            "user_id",
            "campaign_id",
            "week",
            F.col("total_distance_m").cast("double").alias("total_distance_m"),
            F.col("total_kg_co2e").cast("double").alias("total_kg_co2e"),
            "carbon_policy_version",
            "factor_version",
        )
        .join(personal, ["user_id", "campaign_id", "week"], "left")
    )

    weekly_valid = (
        F.col("total_distance_m").isNotNull()
        & (F.col("total_distance_m") > 0)
        & F.col("total_kg_co2e").isNotNull()
        & ~F.isnan("total_kg_co2e")
        & (F.col("total_kg_co2e") >= 0)
    )
    personal_valid = (
        (F.col("personal_status") == F.lit("ready"))
        & (F.col("personal_method") == F.lit("personal_cumulative"))
        & F.col("reference_personal_baseline_g_co2e_per_km").isNotNull()
        & ~F.isnan("reference_personal_baseline_g_co2e_per_km")
        & (F.col("reference_personal_baseline_g_co2e_per_km") >= 0)
    )

    with_metric = joined.withColumn(
        "weekly_carbon_intensity_g_co2e_per_km",
        F.when(
            weekly_valid,
            (F.col("total_kg_co2e") * F.lit(1000.0))
            / (F.col("total_distance_m") / F.lit(1000.0)),
        ),
    )

    valid = weekly_valid & personal_valid
    reduction = (
        F.col("reference_personal_baseline_g_co2e_per_km")
        - F.col("weekly_carbon_intensity_g_co2e_per_km")
    )

    return (
        with_metric
        .withColumn(
            "reduction_g_co2e_per_km",
            F.when(valid, reduction),
        )
        .withColumn(
            "reduction_rate",
            F.when(
                valid & (F.col("reference_personal_baseline_g_co2e_per_km") > 0),
                reduction / F.col("reference_personal_baseline_g_co2e_per_km"),
            ),
        )
        .withColumn(
            "status",
            F.when(~weekly_valid, F.lit("insufficient_data"))
            .when(~personal_valid, F.lit("insufficient_data"))
            .when(reduction > 0, F.lit("changed"))
            .otherwise(F.lit("no_change")),
        )
        .withColumn(
            "reason",
            F.when(~weekly_valid, F.lit("weekly_summary_invalid"))
            .when(~personal_valid, F.lit("personal_baseline_not_ready"))
            .when(reduction > 0, F.lit("weekly_carbon_intensity_below_personal_baseline"))
            .otherwise(F.lit("weekly_carbon_intensity_not_below_personal_baseline")),
        )
        .withColumn("policy_version", F.lit(policy["policy_version"]))
        .withColumn("generated_at", F.current_timestamp())
        .select(
            "user_id",
            "campaign_id",
            "week",
            "total_distance_m",
            "total_kg_co2e",
            "weekly_carbon_intensity_g_co2e_per_km",
            "reference_personal_baseline_g_co2e_per_km",
            "reduction_g_co2e_per_km",
            "reduction_rate",
            "status",
            "reason",
            "policy_version",
            "baseline_policy_version",
            "eligibility_policy_version",
            "carbon_policy_version",
            "factor_version",
            "generated_at",
        )
    )


def write_gold(df):
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(GOLD_BEHAVIOR_CHANGE_PATH)
    )


def verify(spark, campaign_id: str, week: str) -> bool:
    df = spark.read.format("delta").load(GOLD_BEHAVIOR_CHANGE_PATH)
    count = df.filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week)).count()
    print(f"[verify] campaign_id={campaign_id} week={week} behavior_change rows={count}")
    return count > 0


def run(campaign_id: str, week: str):
    spark = SparkSession.builder.getOrCreate()
    policy = load_policy(BEHAVIOR_CHANGE_POLICY_PATH)

    weekly = (
        spark.read.format("delta").load(GOLD_WEEKLY_USER_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
    )
    personal = (
        spark.read.format("delta").load(GOLD_PERSONAL_BASELINE_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
    )

    result = build_behavior_change(weekly, personal, policy)
    write_gold(result)

    if not verify(spark, campaign_id, week):
        raise RuntimeError(f"campaign_id={campaign_id} week={week}: behavior change verification failed")

    print(
        f"[done] campaign_id={campaign_id} week={week} behavior change complete "
        f"(policy_version={policy['policy_version']})"
    )


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None
    if not campaign_id_arg or not week_arg:
        raise ValueError("campaign_id and week parameters required")
    run(campaign_id_arg, week_arg)

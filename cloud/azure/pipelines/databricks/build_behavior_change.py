from __future__ import annotations

import os
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

from behavior_change_policy import classify_behavior_change

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

OUTPUT_SCHEMA = StructType([
    StructField("user_id", StringType(), False),
    StructField("campaign_id", StringType(), False),
    StructField("week", StringType(), False),
    StructField("total_distance_m", DoubleType(), True),
    StructField("total_kg_co2e", DoubleType(), True),
    StructField("weekly_carbon_intensity_g_co2e_per_km", DoubleType(), True),
    StructField("reference_personal_baseline_g_co2e_per_km", DoubleType(), True),
    StructField("reduction_g_co2e_per_km", DoubleType(), True),
    StructField("reduction_rate", DoubleType(), True),
    StructField("status", StringType(), False),
    StructField("reason", StringType(), False),
    StructField("policy_version", StringType(), False),
    StructField("baseline_policy_version", StringType(), True),
    StructField("eligibility_policy_version", StringType(), True),
    StructField("carbon_policy_version", StringType(), True),
    StructField("factor_version", StringType(), True),
    StructField("generated_at", StringType(), False),
])


def load_policy(path: str) -> dict:
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _weekly_metric(total_kg_co2e, total_distance_m):
    if total_kg_co2e is None or total_distance_m is None:
        return None
    try:
        carbon = float(total_kg_co2e)
        distance_m = float(total_distance_m)
    except (TypeError, ValueError):
        return None
    if carbon < 0 or distance_m <= 0:
        return None
    return (carbon * 1000.0) / (distance_m / 1000.0)


def build_behavior_change(weekly_user_df, personal_baseline_df, policy: dict):
    """Build one mission-independent Behavior Change row per user/campaign/week."""
    personal = personal_baseline_df.select(
        "user_id",
        "campaign_id",
        "week",
        F.col("status").alias("personal_status"),
        F.col("method").alias("personal_method"),
        F.col("value").alias("personal_value"),
        F.col("policy_version").alias("baseline_policy_version"),
        F.col("eligibility_policy_version").alias("eligibility_policy_version"),
    )

    joined = weekly_user_df.select(
        "user_id",
        "campaign_id",
        "week",
        F.col("total_distance_m").cast("double").alias("total_distance_m"),
        F.col("total_kg_co2e").cast("double").alias("total_kg_co2e"),
        "carbon_policy_version",
        "factor_version",
    ).join(personal, ["user_id", "campaign_id", "week"], "left")

    rows = []
    generated_at = datetime.now(timezone.utc).isoformat()
    for row in joined.collect():
        weekly_intensity = _weekly_metric(row["total_kg_co2e"], row["total_distance_m"])
        result = classify_behavior_change(
            weekly_carbon_intensity_g_per_km=weekly_intensity,
            personal_baseline_g_per_km=row["personal_value"],
            personal_status=row["personal_status"],
            personal_method=row["personal_method"],
        )
        rows.append({
            "user_id": row["user_id"],
            "campaign_id": row["campaign_id"],
            "week": row["week"],
            "total_distance_m": row["total_distance_m"],
            "total_kg_co2e": row["total_kg_co2e"],
            "weekly_carbon_intensity_g_co2e_per_km": weekly_intensity,
            "reference_personal_baseline_g_co2e_per_km": row["personal_value"],
            "reduction_g_co2e_per_km": result["reduction_g_co2e_per_km"],
            "reduction_rate": result["reduction_rate"],
            "status": result["status"],
            "reason": result["reason"],
            "policy_version": policy["policy_version"],
            "baseline_policy_version": row["baseline_policy_version"],
            "eligibility_policy_version": row["eligibility_policy_version"],
            "carbon_policy_version": row["carbon_policy_version"],
            "factor_version": row["factor_version"],
            "generated_at": generated_at,
        })

    spark = weekly_user_df.sparkSession
    return spark.createDataFrame(rows, schema=OUTPUT_SCHEMA) if rows else spark.createDataFrame([], schema=OUTPUT_SCHEMA)


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

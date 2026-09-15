import os

import pandas as pd
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

BASELINE_POLICY_PATH = os.environ.get(
    "CANOPY_BASELINE_POLICY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/baseline_policy.yaml",
)

BASELINE_SCHEMA = (
    "user_id string, campaign_id string, week string, "
    "cumulative_g_co2e double, cumulative_distance_km double, "
    "baseline_g_co2e_per_km double, method string, policy_version string"
)


def load_policy(path):
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compute_personal_baseline(pdf, policy_version):
    pdf = pdf.sort_values("week").reset_index(drop=True)
    pdf["g_co2e"] = pdf["total_kg_co2e"] * 1000.0
    pdf["distance_km"] = pdf["total_distance_m"] / 1000.0

    cumulative_g_prior = pdf["g_co2e"].cumsum().shift(1)
    cumulative_km_prior = pdf["distance_km"].cumsum().shift(1)

    out_rows = []
    for i, row in pdf.iterrows():
        g_prior = cumulative_g_prior.iloc[i]
        km_prior = cumulative_km_prior.iloc[i]

        has_prior_week = pd.notna(km_prior)
        can_compute = has_prior_week and km_prior > 0

        if can_compute:
            baseline = g_prior / km_prior
            method = "personal_cumulative"
        else:
            baseline = None
            method = "population_fallback"
            g_prior = g_prior if pd.notna(g_prior) else None
            km_prior = km_prior if pd.notna(km_prior) else None

        out_rows.append({
            "user_id": row["user_id"],
            "campaign_id": row["campaign_id"],
            "week": row["week"],
            "cumulative_g_co2e": g_prior,
            "cumulative_distance_km": km_prior,
            "baseline_g_co2e_per_km": baseline,
            "method": method,
            "policy_version": policy_version,
        })

    return pd.DataFrame(out_rows)


def build_personal_baseline(weekly_user_df, policy_version):
    def _apply(pdf):
        return _compute_personal_baseline(pdf, policy_version)

    return weekly_user_df.groupBy("user_id", "campaign_id").applyInPandas(_apply, schema=BASELINE_SCHEMA)


def write_gold(df, path):
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .partitionBy("campaign_id")
        .save(path)
    )


def verify(spark, campaign_id):
    df = spark.read.format("delta").load(GOLD_PERSONAL_BASELINE_PATH)
    count = df.filter(F.col("campaign_id") == campaign_id).count()
    print(f"[verify] campaign_id={campaign_id} personal_baseline rows={count}")
    return count > 0


def run(campaign_id):
    spark = SparkSession.builder.getOrCreate()
    policy = load_policy(BASELINE_POLICY_PATH)

    weekly_user = spark.read.format("delta").load(GOLD_WEEKLY_USER_PATH)
    weekly_user = weekly_user.filter(F.col("campaign_id") == campaign_id)

    baseline = build_personal_baseline(weekly_user, policy["policy_version"])
    write_gold(baseline, GOLD_PERSONAL_BASELINE_PATH)

    ok = verify(spark, campaign_id)
    if not ok:
        raise RuntimeError(f"campaign_id={campaign_id}: personal_baseline verification failed")

    print(f"[done] campaign_id={campaign_id} personal_baseline complete (policy_version={policy['policy_version']})")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if not campaign_id_arg:
        raise ValueError("campaign_id parameter required")

    run(campaign_id_arg)

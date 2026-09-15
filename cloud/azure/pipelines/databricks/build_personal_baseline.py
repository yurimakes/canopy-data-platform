import os

import pandas as pd
import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from baseline_eligibility import (
    evaluate_personal_eligibility, finite_nonnegative, load_eligibility_policy,
    load_identities, observation_context, week_evaluation_time,
)

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
    "baseline_g_co2e_per_km double, method string, policy_version string, "
    "status string, value double, eligibility_policy_version string, "
    "observation_days long, confirmed_trip_count long, observation_source string, "
    "eligibility_reason string, primary_baseline string"
)


def load_policy(path):
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compute_personal_baseline(pdf, policy_version, eligibility_policy=None, identities=None,
                               commute_scope_verified=False):
    eligibility_policy = eligibility_policy or load_eligibility_policy()
    identities = identities or {"users": [], "memberships": []}
    if pdf.duplicated(["user_id", "campaign_id", "week"]).any():
        raise ValueError("Duplicate Weekly Gold rows; expected one row per user/campaign/week")
    pdf = pdf.sort_values("week").reset_index(drop=True)
    pdf["g_co2e"] = pd.to_numeric(pdf["total_kg_co2e"], errors="coerce") * 1000.0
    pdf["distance_km"] = pd.to_numeric(pdf["total_distance_m"], errors="coerce") / 1000.0

    cumulative_g_prior = pdf["g_co2e"].cumsum().shift(1)
    cumulative_km_prior = pdf["distance_km"].cumsum().shift(1)

    out_rows = []
    for i, row in pdf.iterrows():
        g_prior = cumulative_g_prior.iloc[i]
        km_prior = cumulative_km_prior.iloc[i]

        # Use the same prior-completed-week history as the existing formula.
        history = pdf.iloc[:i]
        def valid_total(column):
            values = history[column].tolist() if column in history else [None]
            if column == "trip_count" and any(not finite_nonnegative(v) or int(v) != v for v in values):
                return None
            return sum(values) if all(finite_nonnegative(v) for v in values) else None

        days, source, identity_error = observation_context(
            row["user_id"], row["campaign_id"], week_evaluation_time(row["week"]), identities)
        trip_count = valid_total("trip_count")
        gate = evaluate_personal_eligibility(days, trip_count, valid_total("total_distance_m"),
                                            valid_total("total_kg_co2e"), eligibility_policy)
        if identity_error:
            gate["reasons"].append(identity_error)
        if not commute_scope_verified:
            gate["reasons"].append("weekly_commute_scope_unverified")
        if gate["reasons"]:
            gate["status"] = eligibility_policy["personal"]["status"]["before_eligible"]

        has_prior_week = pd.notna(km_prior)
        can_compute = (gate["status"] == eligibility_policy["personal"]["status"]["when_eligible"]
                       and has_prior_week and km_prior > 0 and finite_nonnegative(g_prior)
                       and finite_nonnegative(km_prior))

        if can_compute:
            baseline = g_prior / km_prior
            method = "personal_cumulative"
            if not finite_nonnegative(baseline):
                can_compute = False
                baseline = None
                method = "population_fallback"
                gate["reasons"].append("invalid_calculated_value")
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
            "status": eligibility_policy["personal"]["status"]["when_eligible" if can_compute else "before_eligible"],
            "value": baseline,
            "eligibility_policy_version": gate["policy_version"],
            "observation_days": days,
            "confirmed_trip_count": int(trip_count) if finite_nonnegative(trip_count) and int(trip_count) == trip_count else None,
            "observation_source": source,
            "eligibility_reason": ",".join(gate["reasons"]) or None,
            "primary_baseline": None if can_compute else eligibility_policy["personal"]["cold_start"]["primary_baseline"],
        })

    return pd.DataFrame(out_rows)


def build_personal_baseline(weekly_user_df, policy_version, eligibility_policy=None, identities=None,
                            commute_scope_verified=None):
    eligibility_policy = eligibility_policy or load_eligibility_policy()
    if identities is None:
        keys = weekly_user_df.select("user_id", "campaign_id").distinct().collect()
        identities = {"users": [], "memberships": []}
        for campaign_id in sorted({r.campaign_id for r in keys}):
            context = load_identities(campaign_id=campaign_id,
                                      user_ids=[r.user_id for r in keys if r.campaign_id == campaign_id])
            identities["memberships"].extend(context["memberships"])
            # The same user may participate in more than one campaign.
            by_user = {r.get("user_id", r.get("id")): r for r in identities["users"] + context["users"]}
            identities["users"] = list(by_user.values())
    if commute_scope_verified is None:
        commute_scope_verified = os.environ.get("CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED") == "true"
    def _apply(pdf):
        return _compute_personal_baseline(pdf, policy_version, eligibility_policy, identities,
                                           commute_scope_verified)

    return weekly_user_df.groupBy("user_id", "campaign_id").applyInPandas(_apply, schema=BASELINE_SCHEMA)


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

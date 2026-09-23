from datetime import datetime, timedelta

import pandas as pd
from pyspark.sql import DataFrame, SparkSession, functions as F

BEHAVIOR_CHANGE_POLICY = {
    "policy_version": "behavior-change-policy-v1",
    "before_period_weeks": 2,
    "after_period_weeks": 1,
    "minimum_delta": 0,
}

RESULT_SCHEMA = (
    "user_id string, campaign_id string, week string, "
    "before_week_start string, before_week_end string, "
    "after_week_start string, after_week_end string, "
    "before_avg_weekly_kg_co2e double, after_avg_weekly_kg_co2e double, "
    "change_kg_co2e double, change_rate double, "
    "status string, reason string, policy_version string"
)


def _iso_week_to_monday(week_label):
    year, week = week_label.split("-W")
    return datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()


def _week_date_range(week_labels):
    mondays = [_iso_week_to_monday(w) for w in week_labels]
    start = min(mondays)
    end = max(mondays) + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _compute_rolling_for_user(pdf, before_weeks, after_weeks, minimum_delta, policy_version):
    pdf = pdf.sort_values("week").reset_index(drop=True)
    weeks = pdf["week"].tolist()
    values = pdf["metric_value"].tolist()
    user_id = pdf["user_id"].iloc[0]
    campaign_id = pdf["campaign_id"].iloc[0]

    out_rows = []
    for i in range(len(pdf)):
        after_start_idx = i - after_weeks + 1
        after_end_idx = i
        before_end_idx = after_start_idx - 1
        before_start_idx = before_end_idx - before_weeks + 1

        if after_start_idx < 0 or before_start_idx < 0:
            out_rows.append({
                "user_id": user_id, "campaign_id": campaign_id, "week": weeks[i],
                "before_week_start": None, "before_week_end": None,
                "after_week_start": None, "after_week_end": None,
                "before_avg_weekly_kg_co2e": None, "after_avg_weekly_kg_co2e": None,
                "change_kg_co2e": None, "change_rate": None,
                "status": "insufficient_data", "reason": "missing before or after period data",
                "policy_version": policy_version,
            })
            continue

        before_weeks_list = weeks[before_start_idx:before_end_idx + 1]
        after_weeks_list = weeks[after_start_idx:after_end_idx + 1]
        before_vals = values[before_start_idx:before_end_idx + 1]
        after_vals = values[after_start_idx:after_end_idx + 1]

        before_avg = sum(before_vals) / len(before_vals)
        after_avg = sum(after_vals) / len(after_vals)
        before_week_start, before_week_end = _week_date_range(before_weeks_list)
        after_week_start, after_week_end = _week_date_range(after_weeks_list)

        change_kg = before_avg - after_avg
        change_rate = (change_kg / before_avg) if before_avg else None

        if change_kg > minimum_delta:
            status = "changed"
            reason = f"before({before_avg}) - after({after_avg}) > minimum_delta({minimum_delta})"
        else:
            status = "no_change"
            reason = f"before({before_avg}) - after({after_avg}) <= minimum_delta({minimum_delta})"

        out_rows.append({
            "user_id": user_id, "campaign_id": campaign_id, "week": weeks[i],
            "before_week_start": before_week_start, "before_week_end": before_week_end,
            "after_week_start": after_week_start, "after_week_end": after_week_end,
            "before_avg_weekly_kg_co2e": before_avg, "after_avg_weekly_kg_co2e": after_avg,
            "change_kg_co2e": change_kg, "change_rate": change_rate,
            "status": status, "reason": reason, "policy_version": policy_version,
        })

    return pd.DataFrame(out_rows)


def build_behavior_change(weekly_gold: DataFrame) -> DataFrame:
    """Build the observed weekly Behavior Change KPI from Weekly Gold.

    This is an observational before/after KPI. It does not estimate a causal
    effect of CANOPY interventions.
    """
    policy = BEHAVIOR_CHANGE_POLICY
    before_weeks = policy["before_period_weeks"]
    after_weeks = policy["after_period_weeks"]
    minimum_delta = policy["minimum_delta"]
    policy_version = policy["policy_version"]

    metric_df = weekly_gold.select(
        "user_id",
        "campaign_id",
        "week",
        F.col("total_kg_co2e").alias("metric_value"),
    )

    def _apply(pdf):
        return _compute_rolling_for_user(
            pdf,
            before_weeks,
            after_weeks,
            minimum_delta,
            policy_version,
        )

    return (
        metric_df
        .groupBy("user_id", "campaign_id")
        .applyInPandas(_apply, schema=RESULT_SCHEMA)
    )


def behavior_change() -> DataFrame:
    """Backward-compatible standalone wrapper."""
    spark = SparkSession.getActiveSession()
    if spark is None:
        spark = SparkSession.builder.getOrCreate()

    return build_behavior_change(
        spark.read.table("weekly_gold")
    )

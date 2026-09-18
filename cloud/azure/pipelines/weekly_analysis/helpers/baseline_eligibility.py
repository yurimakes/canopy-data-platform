from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from pyspark.sql import DataFrame, Window, functions as F
from pyspark.sql.functions import pandas_udf
from pyspark.sql.types import StructType


def _as_nullable_number(value):
    if value is None or pd.isna(value):
        return None
    return value


def _as_nullable_int(value):
    value = _as_nullable_number(value)
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or not numeric.is_integer():
        return None
    return int(numeric)


def build_baseline_eligibility(
    weekly_df: DataFrame,
    policy: Any,
    PERSONAL_ELIGIBILITY_SCHEMA: StructType,
    week_evaluation_time: Callable,
    observation_context: Callable,
    evaluate_personal_eligibility: Callable,
    membership_df: DataFrame | None = None,
    commute_scope_verified: bool = False,
) -> DataFrame:
    """Evaluate Personal Baseline eligibility from prior weekly history.

    The original baseline_eligibility.py policy functions remain the source of
    truth for observation-day and threshold semantics. Lakeflow receives the
    campaign membership snapshot as a DataFrame instead of calling Cosmos from
    inside the transform.

    Weekly totals are evaluated only from previously completed weeks so the
    current evaluation week does not leak into its own eligibility gate.
    """

    keys = ["user_id", "campaign_id", "week"]

    weekly = weekly_df.groupBy(*keys).agg(
        F.sum("trip_count").cast("long").alias("_week_trip_count"),
        F.sum("total_distance_m").cast("double").alias("_week_total_distance"),
        F.sum("total_kg_co2e").cast("double").alias("_week_total_carbon"),
    )

    prior_window = (
        Window
        .partitionBy("user_id", "campaign_id")
        .orderBy("week")
        .rowsBetween(Window.unboundedPreceding, -1)
    )

    history = (
        weekly
        .withColumn(
            "trip_count",
            F.sum("_week_trip_count").over(prior_window),
        )
        .withColumn(
            "total_distance",
            F.sum("_week_total_distance").over(prior_window),
        )
        .withColumn(
            "total_carbon",
            F.sum("_week_total_carbon").over(prior_window),
        )
    )

    if membership_df is None:
        membership_by_user = (
            weekly_df
            .select("user_id", "campaign_id")
            .limit(0)
            .withColumn("joined_at", F.lit(None).cast("string"))
            .withColumn("_membership_count", F.lit(0).cast("long"))
        )
    else:
        membership_by_user = (
            membership_df
            .select(
                F.col("user_id").cast("string").alias("user_id"),
                F.col("campaign_id").cast("string").alias("campaign_id"),
                F.col("joined_at").cast("string").alias("joined_at"),
            )
            .filter(
                F.col("user_id").isNotNull()
                & F.col("campaign_id").isNotNull()
            )
            .groupBy("user_id", "campaign_id")
            .agg(
                F.count("*").cast("long").alias("_membership_count"),
                F.first("joined_at", ignorenulls=True).alias("joined_at"),
            )
        )

    scoped = (
        history
        .join(
            membership_by_user,
            ["user_id", "campaign_id"],
            "left",
        )
        .withColumn(
            "_membership_count",
            F.coalesce(
                F.col("_membership_count"),
                F.lit(0).cast("long"),
            ),
        )
    )

    @pandas_udf(PERSONAL_ELIGIBILITY_SCHEMA)
    def evaluate_personal_row(
        user_id: pd.Series,
        campaign_id: pd.Series,
        week: pd.Series,
        trip_count: pd.Series,
        total_distance: pd.Series,
        total_carbon: pd.Series,
        joined_at: pd.Series,
        membership_count: pd.Series,
    ) -> pd.DataFrame:
        results = []

        for uid, cid, w, tc, td, tc_carb, joined, member_count in zip(
            user_id,
            campaign_id,
            week,
            trip_count,
            total_distance,
            total_carbon,
            joined_at,
            membership_count,
        ):
            evaluated_at = week_evaluation_time(str(w))

            count = _as_nullable_int(member_count) or 0
            membership_record = {
                "user_id": uid,
                "campaign_id": cid,
            }
            if joined is not None and not pd.isna(joined):
                membership_record["joined_at"] = str(joined)

            identities = {
                "users": [],
                "memberships": [
                    dict(membership_record)
                    for _ in range(count)
                ],
            }

            obs_days, source, identity_error = observation_context(
                uid,
                cid,
                evaluated_at,
                identities,
            )

            result = evaluate_personal_eligibility(
                observation_days=obs_days,
                trip_count=_as_nullable_number(tc),
                total_distance=_as_nullable_number(td),
                total_carbon=_as_nullable_number(tc_carb),
                policy=policy,
            )

            reasons = list(result.get("reasons") or [])

            if identity_error and identity_error not in reasons:
                reasons.append(identity_error)

            if (
                not commute_scope_verified
                and "weekly_commute_scope_unverified" not in reasons
            ):
                reasons.append("weekly_commute_scope_unverified")

            status = result.get("status")
            if reasons:
                status = policy["personal"]["status"]["before_eligible"]

            results.append({
                "user_id": uid,
                "campaign_id": cid,
                "week": w,
                "status": status,
                "policy_version": result.get("policy_version"),
                "observation_days": (
                    int(obs_days)
                    if obs_days is not None
                    else None
                ),
                "confirmed_trip_count": _as_nullable_int(
                    result.get("confirmed_trip_count")
                ),
                "observation_source": source,
                "reasons": reasons,
            })

        return pd.DataFrame(results)

    return scoped.select(
        evaluate_personal_row(
            F.col("user_id"),
            F.col("campaign_id"),
            F.col("week"),
            F.col("trip_count"),
            F.col("total_distance"),
            F.col("total_carbon"),
            F.col("joined_at"),
            F.col("_membership_count"),
        ).alias("evaluated")
    ).select("evaluated.*")

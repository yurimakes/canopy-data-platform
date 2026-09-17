from __future__ import annotations

import pandas as pd
from typing import Any, Callable
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import StructType
from pyspark.sql.functions import pandas_udf


def build_baseline_eligibility(
    weekly_df: DataFrame, 
    policy: Any, 
    PERSONAL_ELIGIBILITY_SCHEMA: StructType,
    week_evaluation_time: Callable,
    observation_context: Callable,
    evaluate_personal_eligibility: Callable
) -> DataFrame:
    """주간 트립 데이터를 집계하고 개인별 Baseline 대상 판정을 수행하는 헬퍼 함수"""
    
    agg_df = weekly_df.groupBy("user_id", "campaign_id", "week").agg(
        F.sum("trip_count").alias("trip_count"),
        F.sum("total_distance_m").alias("total_distance"),
        F.sum("total_kg_co2e").alias("total_carbon")
    )

    @pandas_udf(PERSONAL_ELIGIBILITY_SCHEMA)
    def evaluate_personal_row(
        user_id: pd.Series,
        campaign_id: pd.Series,
        week: pd.Series,
        trip_count: pd.Series,
        total_distance: pd.Series,
        total_carbon: pd.Series
    ) -> pd.DataFrame:
        results = []
        for uid, cid, w, tc, td, tc_carb in zip(
            user_id, campaign_id, week, trip_count, total_distance, total_carbon
        ):
            try:
                evaluated_at = week_evaluation_time(w)
            except Exception:
                evaluated_at = None

            identities = {
                "users": [],
                "memberships": []
            }

            obs_days, source, err = observation_context(uid, cid, evaluated_at, identities)
            observation_days = int(obs_days) if obs_days is not None else 0

            result = evaluate_personal_eligibility(
                observation_days=observation_days,
                trip_count=tc or 0,
                total_distance=td or 0.0,
                total_carbon=tc_carb or 0.0,
                policy=policy
            )

            results.append({
                "user_id": uid,
                "campaign_id": cid,
                "week": w,
                "status": result.get("status"),
                "policy_version": result.get("policy_version"),
                "observation_days": observation_days,
                "confirmed_trip_count": int(result.get("confirmed_trip_count", tc or 0)),
                "reasons": result.get("reasons", [])
            })

        return pd.DataFrame(results)

    return agg_df.select(
        evaluate_personal_row(
            F.col("user_id"),
            F.col("campaign_id"),
            F.col("week"),
            F.col("trip_count"),
            F.col("total_distance"),
            F.col("total_carbon")
        ).alias("evaluated")
    ).select("evaluated.*")
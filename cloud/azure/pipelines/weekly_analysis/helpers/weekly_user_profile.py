"""Weekly user profile Spark transformations."""

from __future__ import annotations

import os

from pyspark.sql import DataFrame, SparkSession, functions as F


def build_weekly_user_profile(
    weekly_df: DataFrame,
    mission_df: DataFrame | None = None,
) -> DataFrame:
    """Build one weekly profile row per user/campaign/week.

    mission_df is accepted for the Mission Response integration contract.
    The current profile calculation does not consume its rows yet.
    """

    _ = mission_df

    base_df = weekly_df.groupBy(
        "user_id",
        "campaign_id",
        "week",
    ).agg(
        F.sum("valid_primary_trip_count")
        .cast("int")
        .alias("valid_trip_count"),

        F.sum("invalid_primary_trip_count")
        .cast("int")
        .alias("invalid_trip_count"),

        F.sum("car_primary_trip_count")
        .cast("int")
        .alias("car_primary_trip_count"),

        F.sum("transit_primary_trip_count")
        .cast("int")
        .alias("transit_primary_trip_count"),

        F.sum("low_carbon_trip_count")
        .cast("int")
        .alias("low_carbon_trip_count"),
    )

    return base_df.select(
        F.lit("user_profile").alias("type"),
        F.lit("v1").alias("profile_version"),
        F.lit("active").alias("profile_status"),
        F.col("user_id"),
        F.col("campaign_id"),

        F.col("week").alias("source_week_start"),
        F.col("week").alias("source_week_end"),
        F.col("week").alias("effective_week_start"),

        F.col("valid_trip_count"),
        F.col("invalid_trip_count"),

        F.lit(None)
        .cast("map<string, int>")
        .alias("invalid_trip_reasons"),

        F.col("car_primary_trip_count"),

        F.try_divide(
            F.col("car_primary_trip_count"),
            F.col("valid_trip_count"),
        ).alias("car_ratio"),

        F.lit(0)
        .cast("int")
        .alias("short_car_trip_count"),

        F.lit(0.0).alias("short_car_share"),

        F.col("transit_primary_trip_count"),
        F.col("low_carbon_trip_count"),

        F.lit(0.0).alias("carbon_change_rate"),

        F.lit("delta_sync").alias("mission_history_source"),

        F.lit(0)
        .cast("int")
        .alias("preference_positive_evidence_count"),

        F.lit("{}").alias("category_preferences_json"),
        F.lit("{}").alias("difficulty_state_json"),
        F.lit("{}").alias("family_capability_json"),

        F.lit(None)
        .cast("string")
        .alias("profile_hash"),
    )


def weekly_user_profile() -> DataFrame:
    """Backward-compatible standalone wrapper."""

    spark = SparkSession.getActiveSession()
    if spark is None:
        spark = SparkSession.builder.getOrCreate()

    weekly_df = spark.read.table(
        "dbw_canopy_dev.weekly_analysis_scaffold.weekly_gold"
    )

    mission_response_path = os.environ.get(
        "CANOPY_GOLD_MISSION_RESPONSE_PATH",
        "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_response_weekly/",
    )

    try:
        mission_df = (
            spark.read
            .format("delta")
            .load(mission_response_path)
        )
    except Exception:
        mission_df = None

    return build_weekly_user_profile(
        weekly_df=weekly_df,
        mission_df=mission_df,
    )
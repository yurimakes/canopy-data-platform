from __future__ import annotations

import os
from pyspark.sql import SparkSession, functions as F

def weekly_user_profile():
    spark = SparkSession.getActiveSession()
    
    weekly_df = spark.read.table("dbw_canopy_dev.weekly_analysis_scaffold.weekly_gold")
    
    mission_response_path = os.environ.get(
        "CANOPY_GOLD_MISSION_RESPONSE_PATH",
        "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_response_weekly/"
    )
    
    try:
        mission_df = spark.read.format("delta").load(mission_response_path)
    except Exception:
        mission_df = None

    base_df = weekly_df.groupBy("user_id", "campaign_id", "week").agg(
        F.sum("valid_primary_trip_count").alias("valid_trip_count"),
        F.sum("invalid_primary_trip_count").alias("invalid_trip_count"),
        F.sum("car_primary_trip_count").alias("car_primary_trip_count"),
        F.sum("transit_primary_trip_count").alias("transit_primary_trip_count"),
        F.sum("low_carbon_trip_count").alias("low_carbon_trip_count"),
    )

    profile_df = base_df.select(
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
        F.lit(None).cast("map<string, int>").alias("invalid_trip_reasons"),
        F.col("car_primary_trip_count"),
        (F.col("car_primary_trip_count") / F.greatest(F.col("valid_trip_count"), F.lit(1))).alias("car_ratio"),
        F.lit(0).alias("short_car_trip_count"),
        F.lit(0.0).alias("short_car_share"),
        F.col("transit_primary_trip_count"),
        F.col("low_carbon_trip_count"),
        F.lit(0.0).alias("carbon_change_rate"),
        F.lit("delta_sync").alias("mission_history_source"),
        F.lit(0).alias("preference_positive_evidence_count"),
        F.lit("{}").alias("category_preferences_json"),
        F.lit("{}").alias("difficulty_state_json"),
        F.lit("{}").alias("family_capability_json"),
        F.lit(None).cast("string").alias("profile_hash")
    )

    return profile_df
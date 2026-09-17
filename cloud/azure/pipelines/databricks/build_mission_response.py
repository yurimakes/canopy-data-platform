from pyspark.sql import functions as F

RESPONSE_VERSION = "mission-response-v1"


def flatten_bundles(bundles_df):
    exploded = bundles_df.select(
        "campaign_id", "user_id", "week_start", "week_end", "bundle_id",
        "common_target_count", "policy_version",
        F.explode("missions").alias("mission"),
    )
    exploded = exploded.withColumn("_week_start_date", F.to_date("week_start"))
    exploded = exploded.withColumn("_iso_thursday", F.date_add(F.col("_week_start_date"), 3))
    exploded = exploded.withColumn(
        "week",
        F.concat(
            F.year("_iso_thursday").cast("string"), F.lit("-W"),
            F.lpad(F.weekofyear("_week_start_date").cast("string"), 2, "0"),
        ),
    )

    return exploded.select(
        "campaign_id", "user_id", "week", "week_start", "week_end",
        "bundle_id",
        F.col("mission.assignment_id").alias("assignment_id"),
        F.col("mission.mission_template_id").alias("mission_template_id"),
        F.col("mission.mission_family").alias("mission_family"),
        F.col("mission.category_id").alias("category_id"),
        F.col("mission.difficulty_band").alias("difficulty_band"),
        "common_target_count",
        F.col("mission.target_count").alias("target_count"),
        F.coalesce(F.col("mission.affinity_comparable"), F.col("mission.preference_comparable")).alias("affinity_comparable"),
        F.coalesce(F.col("mission.difficulty_comparable"), F.col("mission.preference_comparable")).alias("difficulty_comparable"),
        F.col("mission.preference_comparable").alias("preference_comparable"),
        F.lit(1).cast("int").alias("mission_shown_count"),
        F.lit(0).cast("int").alias("mission_started_count"),
        F.when(F.col("mission.completed") == True, 1).otherwise(0).cast("int").alias("mission_completed_count"),  # noqa: E712
        F.coalesce(F.col("mission.progress_count"), F.lit(0)).alias("progress_count"),
        F.coalesce(F.col("mission.achievement_rate"), F.lit(0.0)).alias("achievement_rate"),
        F.col("mission.completed").alias("completed"),
        F.lit(0).alias("linked_trip_count"),
        "policy_version",
        F.lit(RESPONSE_VERSION).alias("response_version"),
    )

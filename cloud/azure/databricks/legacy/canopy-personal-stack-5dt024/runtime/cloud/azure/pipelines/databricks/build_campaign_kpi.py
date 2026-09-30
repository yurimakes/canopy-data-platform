from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

spark = SparkSession.builder.getOrCreate()

CAMPAIGN_KPI_POLICY_VERSION = "campaign-kpi-v1"


def _week_label_to_end_date(week_label):
    if week_label is None:
        return None
    year, week = week_label.split("-W")
    monday = datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()
    return (monday + timedelta(days=6)).isoformat()


_week_label_to_end_date_udf = F.udf(_week_label_to_end_date, T.StringType())


def read_enrollment(trip_metrics):
    membership = spark.read.table("campaign_membership_raw")

    week_spine = trip_metrics.select("campaign_id", "week").distinct()
    week_spine = week_spine.withColumn("week_end_date", _week_label_to_end_date_udf(F.col("week")))

    joined = week_spine.join(membership, "campaign_id")
    joined = joined.filter(F.to_date(F.col("joined_at")) <= F.to_date(F.col("week_end_date")))
    joined = joined.filter(
        F.col("left_at").isNull() | (F.to_date(F.col("left_at")) > F.to_date(F.col("week_end_date")))
    )

    return joined.groupBy("campaign_id", "week").agg(
        F.countDistinct("user_id").alias("enrolled_user_count"),
    )


def campaign_kpi():
    weekly_gold = spark.read.table("weekly_gold")
    mission = spark.read.table("mission_response_weekly")
    behavior = spark.read.table("behavior_change")
    reward = spark.read.table("reward_ledger_history").filter(F.col("status").isin(["paid", "adjusted"]))

    trip_metrics = weekly_gold.groupBy("campaign_id", "week").agg(
        F.countDistinct(F.when(F.col("trip_count") > 0, F.col("user_id"))).alias("active_user_count"),
        F.sum("trip_count").alias("trip_count"),
        F.sum("total_distance_m").alias("total_distance_m"),
        F.sum("total_kg_co2e").alias("total_kg_co2e"),
    )

    mission_metrics = mission.groupBy("campaign_id", "week").agg(
        F.count("*").alias("assigned_mission_count"),
        F.sum(F.when(F.col("completed") == True, 1).otherwise(0)).alias("completed_mission_count"),  # noqa: E712
    ).withColumn(
        "mission_completion_rate",
        F.when(F.col("assigned_mission_count") > 0, F.col("completed_mission_count") / F.col("assigned_mission_count")),
    )

    behavior_metrics = behavior.groupBy("campaign_id", "week").agg(
        F.countDistinct(F.when(F.col("status") != "insufficient_data", F.col("user_id"))).alias("behavior_evaluable_user_count"),
        F.countDistinct(F.when(F.col("status") == "changed", F.col("user_id"))).alias("changed_user_count"),
    )

    reward_metrics = reward.groupBy("campaign_id", "week_label").agg(
        F.sum("points").alias("paid_reward_points"),
    ).withColumnRenamed("week_label", "week")

    enrollment_metrics = read_enrollment(trip_metrics)

    result = (
        trip_metrics
        .join(mission_metrics, ["campaign_id", "week"], "left")
        .join(behavior_metrics, ["campaign_id", "week"], "left")
        .join(reward_metrics, ["campaign_id", "week"], "left")
        .join(enrollment_metrics, ["campaign_id", "week"], "left")
        .withColumn(
            "participation_rate",
            F.when(F.col("enrolled_user_count") > 0, F.col("active_user_count") / F.col("enrolled_user_count")),
        )
        .withColumn("policy_version", F.lit(CAMPAIGN_KPI_POLICY_VERSION))
        .withColumn("generated_at", F.lit(datetime.now(timezone.utc)))
    )

    return result.select(
        "campaign_id", "week", "enrolled_user_count", "active_user_count",
        "participation_rate", "trip_count", "total_distance_m", "total_kg_co2e",
        "assigned_mission_count", "completed_mission_count", "mission_completion_rate",
        "changed_user_count", "behavior_evaluable_user_count", "paid_reward_points",
        "policy_version", "generated_at",
    )


def run():
    result = campaign_kpi()
    result.write.format("delta").mode("overwrite").saveAsTable("campaign_kpi")

    count = spark.read.table("campaign_kpi").count()
    print(f"[done] campaign_kpi rows={count}")


if __name__ == "__main__":
    run()

"""Spark transformations for CANOPY weekly Campaign KPI.

This module only transforms input DataFrames.
It does not read/write ADLS, Cosmos DB, or Lakeflow tables directly.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, functions as F


CAMPAIGN_KPI_POLICY_VERSION = "campaign-kpi-v1"


def _require_columns(df: DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            f"{name} missing required columns: {', '.join(missing)}"
        )


def _week_spine(weekly_gold: DataFrame) -> DataFrame:
    """Build campaign/week scopes with ISO-week Monday/Sunday dates."""

    scopes = (
        weekly_gold
        .select("campaign_id", "week")
        .filter(
            F.col("campaign_id").isNotNull()
            & F.col("week").isNotNull()
        )
        .distinct()
        .withColumn(
            "_iso_week",
            F.substring(F.col("week"), 7, 2).cast("int"),
        )
        .withColumn(
            "_jan4",
            F.to_date(
                F.concat(
                    F.substring(F.col("week"), 1, 4),
                    F.lit("-01-04"),
                )
            ),
        )
        .withColumn(
            "_week1_monday",
            F.expr(
                "date_add(_jan4, -pmod(dayofweek(_jan4) + 5, 7))"
            ),
        )
        .withColumn(
            "week_start_date",
            F.expr(
                "date_add(_week1_monday, 7 * (_iso_week - 1))"
            ),
        )
        .withColumn(
            "week_end_date",
            F.expr("date_add(week_start_date, 6)"),
        )
    )

    return scopes.select(
        "campaign_id",
        "week",
        "week_start_date",
        "week_end_date",
    )


def _mission_metrics(
    mission_response: DataFrame,
    week_spine: DataFrame,
) -> DataFrame:
    _require_columns(
        mission_response,
        {"campaign_id", "completed"},
        "mission_response",
    )

    if "week" in mission_response.columns:
        scoped = mission_response.select(
            "campaign_id",
            "week",
            "completed",
        )
    else:
        _require_columns(
            mission_response,
            {"week_start", "week_end"},
            "mission_response",
        )

        scoped = (
            mission_response.alias("m")
            .join(
                week_spine.alias("s"),
                (
                    F.col("m.campaign_id")
                    == F.col("s.campaign_id")
                )
                & (
                    F.to_date(F.col("m.week_start"))
                    == F.col("s.week_start_date")
                )
                & (
                    F.to_date(F.col("m.week_end"))
                    == F.col("s.week_end_date")
                ),
                "inner",
            )
            .select(
                F.col("s.campaign_id").alias("campaign_id"),
                F.col("s.week").alias("week"),
                F.col("m.completed").alias("completed"),
            )
        )

    return (
        scoped
        .groupBy("campaign_id", "week")
        .agg(
            F.count("*")
            .cast("long")
            .alias("assigned_mission_count"),

            F.sum(
                F.when(
                    F.col("completed") == F.lit(True),
                    F.lit(1),
                ).otherwise(F.lit(0))
            )
            .cast("long")
            .alias("completed_mission_count"),
        )
    )


def _behavior_metrics(behavior_change: DataFrame) -> DataFrame:
    _require_columns(
        behavior_change,
        {"campaign_id", "week", "user_id", "status"},
        "behavior_change",
    )

    return (
        behavior_change
        .groupBy("campaign_id", "week")
        .agg(
            F.countDistinct(
                F.when(
                    F.col("status") != "insufficient_data",
                    F.col("user_id"),
                )
            )
            .cast("long")
            .alias("behavior_evaluable_user_count"),

            F.countDistinct(
                F.when(
                    F.col("status") == "changed",
                    F.col("user_id"),
                )
            )
            .cast("long")
            .alias("changed_user_count"),
        )
    )


def _reward_metrics(reward_ledger: DataFrame) -> DataFrame:
    _require_columns(
        reward_ledger,
        {"campaign_id", "week_label", "points", "status"},
        "reward_ledger",
    )

    return (
        reward_ledger
        .filter(F.col("status").isin("paid", "adjusted"))
        .groupBy("campaign_id", "week_label")
        .agg(
            F.sum(F.col("points").cast("double"))
            .alias("paid_reward_points")
        )
        .withColumnRenamed("week_label", "week")
    )


def _enrollment_metrics(
    campaign_membership: DataFrame,
    week_spine: DataFrame,
) -> DataFrame:
    _require_columns(
        campaign_membership,
        {"user_id", "campaign_id", "joined_at", "left_at"},
        "campaign_membership",
    )

    return (
        week_spine.alias("s")
        .join(
            campaign_membership.alias("m"),
            (
                F.col("s.campaign_id")
                == F.col("m.campaign_id")
            )
            & F.col("m.joined_at").isNotNull()
            & (
                F.to_date(F.col("m.joined_at"))
                <= F.col("s.week_end_date")
            )
            & (
                F.col("m.left_at").isNull()
                | (
                    F.to_date(F.col("m.left_at"))
                    > F.col("s.week_end_date")
                )
            ),
            "left",
        )
        .groupBy(
            F.col("s.campaign_id").alias("campaign_id"),
            F.col("s.week").alias("week"),
        )
        .agg(
            F.countDistinct(F.col("m.user_id"))
            .cast("long")
            .alias("enrolled_user_count")
        )
    )


def build_campaign_kpi(
    weekly_gold: DataFrame,
    mission_response: DataFrame,
    behavior_change: DataFrame,
    reward_ledger: DataFrame,
    campaign_membership: DataFrame,
    *,
    policy_version: str = CAMPAIGN_KPI_POLICY_VERSION,
) -> DataFrame:
    """Build one Campaign KPI row per campaign/week."""

    _require_columns(
        weekly_gold,
        {
            "user_id",
            "campaign_id",
            "week",
            "trip_count",
            "total_distance_m",
            "total_kg_co2e",
        },
        "weekly_gold",
    )

    week_spine = _week_spine(weekly_gold)

    trip_metrics = (
        weekly_gold
        .groupBy("campaign_id", "week")
        .agg(
            F.countDistinct(
                F.when(
                    F.col("trip_count") > 0,
                    F.col("user_id"),
                )
            )
            .cast("long")
            .alias("active_user_count"),

            F.sum(F.col("trip_count"))
            .cast("long")
            .alias("trip_count"),

            F.sum(F.col("total_distance_m"))
            .cast("double")
            .alias("total_distance_m"),

            F.sum(F.col("total_kg_co2e"))
            .cast("double")
            .alias("total_kg_co2e"),
        )
    )

    mission_metrics = _mission_metrics(
        mission_response,
        week_spine,
    )
    behavior_metrics = _behavior_metrics(behavior_change)
    reward_metrics = _reward_metrics(reward_ledger)
    enrollment_metrics = _enrollment_metrics(
        campaign_membership,
        week_spine,
    )

    result = (
        trip_metrics
        .join(
            enrollment_metrics,
            ["campaign_id", "week"],
            "left",
        )
        .join(
            mission_metrics,
            ["campaign_id", "week"],
            "left",
        )
        .join(
            behavior_metrics,
            ["campaign_id", "week"],
            "left",
        )
        .join(
            reward_metrics,
            ["campaign_id", "week"],
            "left",
        )
        .withColumn(
            "assigned_mission_count",
            F.coalesce(
                F.col("assigned_mission_count"),
                F.lit(0).cast("long"),
            ),
        )
        .withColumn(
            "completed_mission_count",
            F.coalesce(
                F.col("completed_mission_count"),
                F.lit(0).cast("long"),
            ),
        )
        .withColumn(
            "paid_reward_points",
            F.coalesce(
                F.col("paid_reward_points"),
                F.lit(0.0),
            ),
        )
        .withColumn(
            "participation_rate",
            F.when(
                F.col("enrolled_user_count") > 0,
                F.try_divide(
                    F.col("active_user_count"),
                    F.col("enrolled_user_count"),
                ),
            ),
        )
        .withColumn(
            "mission_completion_rate",
            F.when(
                F.col("assigned_mission_count") > 0,
                F.try_divide(
                    F.col("completed_mission_count"),
                    F.col("assigned_mission_count"),
                ),
            ),
        )
        .withColumn(
            "policy_version",
            F.lit(policy_version),
        )
        .withColumn(
            "generated_at",
            F.current_timestamp(),
        )
    )

    return result.select(
        "campaign_id",
        "week",
        "enrolled_user_count",
        "active_user_count",
        "participation_rate",
        "trip_count",
        "total_distance_m",
        "total_kg_co2e",
        "assigned_mission_count",
        "completed_mission_count",
        "mission_completion_rate",
        "changed_user_count",
        "behavior_evaluable_user_count",
        "paid_reward_points",
        "policy_version",
        "generated_at",
    )
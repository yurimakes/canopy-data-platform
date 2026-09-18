"""Pure Spark DataFrame transformation for weekly Reward Calculation."""

from __future__ import annotations

import math
from numbers import Real

from pyspark.sql import DataFrame, Column, functions as F


REWARD_COLUMNS = (
    "user_id", "campaign_id", "week", "status", "payable", "points",
    "reason", "point_reason", "missions_completed_this_week", "policy_version",
)


def _require_columns(df: DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _conversion_rate(policy: dict) -> float:
    """A missing or unusable reward rate must stop calculation."""
    rate = policy.get("point_formula", {}).get("conversion_rate")
    if (
        isinstance(rate, bool)
        or not isinstance(rate, Real)
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError(
            "reward_policy.yaml point_formula.conversion_rate must be "
            "configured as a positive finite number before Reward Calculation"
        )
    return float(rate)


def _week_spine(weekly_gold: DataFrame) -> DataFrame:
    """Resolve the ISO week to Monday and the next Monday (exclusive)."""
    return (
        weekly_gold.select("campaign_id", "week").distinct()
        .withColumn("_iso_week", F.substring(F.col("week"), 7, 2).cast("int"))
        .withColumn(
            "_jan4",
            F.to_date(F.concat(F.substring(F.col("week"), 1, 4), F.lit("-01-04"))),
        )
        .withColumn(
            "_week1_monday",
            F.expr("date_add(_jan4, -pmod(dayofweek(_jan4) + 5, 7))"),
        )
        .withColumn(
            "_week_start",
            F.expr("date_add(_week1_monday, 7 * (_iso_week - 1))"),
        )
        .withColumn("_week_end_exclusive", F.expr("date_add(_week_start, 7)"))
        .select("campaign_id", "week", "_week_start", "_week_end_exclusive")
    )


def _mission_completions(mission_response: DataFrame, weekly_gold: DataFrame) -> DataFrame:
    _require_columns(
        mission_response,
        {"campaign_id", "user_id", "week_start", "week_end", "completed"},
        "mission_response_weekly",
    )
    matched = (
        mission_response.alias("m")
        .join(
            _week_spine(weekly_gold).alias("w"),
            (F.col("m.campaign_id") == F.col("w.campaign_id"))
            & (F.to_date(F.col("m.week_start")) == F.col("w._week_start"))
            & (F.to_date(F.col("m.week_end")) == F.col("w._week_end_exclusive")),
            "inner",
        )
        .select(
            F.col("m.user_id").alias("user_id"),
            F.col("w.campaign_id").alias("campaign_id"),
            F.col("w.week").alias("week"),
            F.col("m.completed").alias("completed"),
        )
    )
    return matched.groupBy("user_id", "campaign_id", "week").agg(
        F.sum(F.when(F.col("completed") == F.lit(True), 1).otherwise(0))
        .cast("long")
        .alias("missions_completed_this_week")
    )


def _classify_status(
    personal_value: Column,
    global_value: Column,
    actual: Column,
    has_current: Column,
) -> Column:
    """Preserve calculate_reward.py's precedence, with missing current trips guarded."""
    return (
        F.when(
            ~has_current | (personal_value.isNull() & global_value.isNull()),
            F.lit("not_eligible"),
        )
        .when(
            personal_value.isNotNull() & ((personal_value - actual) > 0),
            F.lit("improved"),
        )
        .when(
            global_value.isNotNull() & (actual <= global_value),
            F.lit("maintained"),
        )
        .otherwise(F.lit("no_change"))
    )


def _points_for_status(
    status: Column, delta: Column, policy: dict, rate: float,
) -> Column:
    return (
        F.when(status == "not_eligible", F.lit(None).cast("double"))
        .when(
            status == "no_change",
            F.lit(policy.get("points", {}).get("no_change")).cast("double"),
        )
        .otherwise(F.greatest(delta, F.lit(0.0)) / F.lit(rate))
    )


def build_reward_calculation(
    weekly_gold: DataFrame,
    personal_baseline: DataFrame,
    global_baseline: DataFrame,
    mission_response: DataFrame,
    policy: dict,
) -> DataFrame:
    """Build one reward row per current or ready-personal user and ISO week."""
    rate = _conversion_rate(policy)
    _require_columns(
        weekly_gold,
        {"user_id", "campaign_id", "week", "trip_count", "total_kg_co2e", "total_distance_m"},
        "weekly_gold",
    )
    _require_columns(
        personal_baseline,
        {"user_id", "campaign_id", "week", "status", "value"},
        "personal_baseline",
    )
    _require_columns(
        global_baseline,
        {"campaign_id", "week", "status", "value"},
        "global_baseline",
    )

    keys = ["user_id", "campaign_id", "week"]
    current = weekly_gold.select(
        *keys,
        F.col("trip_count").alias("_trip_count"),
        F.when(
            F.col("total_distance_m") > 0,
            (F.col("total_kg_co2e") * 1000.0)
            / (F.col("total_distance_m") / 1000.0),
        ).cast("double").alias("_actual"),
    )
    personal = (
        personal_baseline.filter(F.col("status") == "ready")
        .select(*keys, F.col("value").cast("double").alias("_personal"))
    )
    global_ready = (
        global_baseline.filter(F.col("status") == "ready")
        .select("campaign_id", "week", F.col("value").cast("double").alias("_global"))
    )
    users = current.select(*keys).unionByName(personal.select(*keys)).distinct()
    joined = (
        users.join(current, keys, "left")
        .join(personal, keys, "left")
        .join(global_ready, ["campaign_id", "week"], "left")
        .join(_mission_completions(mission_response, weekly_gold), keys, "left")
    )

    has_current = (
        F.coalesce(F.col("_trip_count") > 0, F.lit(False))
        & F.col("_actual").isNotNull()
    )
    classified = joined.withColumn(
        "status",
        _classify_status(
            F.col("_personal"), F.col("_global"), F.col("_actual"), has_current,
        ),
    )
    delta = F.when(
        F.col("status") == "improved",
        F.col("_personal") - F.col("_actual"),
    ).otherwise(F.col("_global") - F.col("_actual"))
    explained = classified.withColumn("_delta", delta).withColumn(
        "reason",
        F.when(
            F.col("status") == "not_eligible",
            F.when(
                ~has_current,
                F.lit("no eligible current Trip"),
            ).otherwise(F.lit("no personal or global baseline available")),
        )
        .when(
            F.col("status") == "improved",
            F.concat(
                F.lit("personal_baseline("), F.col("_personal").cast("string"),
                F.lit(") - actual("), F.col("_actual").cast("string"),
                F.lit(") > 0"),
            ),
        )
        .when(
            F.col("status") == "maintained",
            F.concat(
                F.lit("actual("), F.col("_actual").cast("string"),
                F.lit(") <= global_baseline("), F.col("_global").cast("string"),
                F.lit(")"),
            ),
        )
        .otherwise(F.lit("no improvement over personal_baseline and not below global_baseline")),
    )
    scored = explained.withColumn(
        "points",
        _points_for_status(F.col("status"), F.col("_delta"), policy, rate),
    ).withColumn(
        "point_reason",
        F.when(F.col("status") == "not_eligible", F.lit("not_eligible"))
        .when(F.col("status") == "no_change", F.lit("policy.points.no_change"))
        .otherwise(
            F.concat(
                F.lit("max(delta="), F.col("_delta").cast("string"),
                F.lit("), 0) / conversion_rate("), F.lit(str(rate)), F.lit(")"),
            )
        ),
    )
    return scored.select(
        F.col("user_id").cast("string").alias("user_id"),
        F.col("campaign_id").cast("string").alias("campaign_id"),
        F.col("week").cast("string").alias("week"),
        F.col("status").cast("string").alias("status"),
        (F.col("status") != "not_eligible").cast("boolean").alias("payable"),
        F.col("points").cast("double").alias("points"),
        F.col("reason").cast("string").alias("reason"),
        F.col("point_reason").cast("string").alias("point_reason"),
        F.coalesce(F.col("missions_completed_this_week"), F.lit(0))
        .cast("long").alias("missions_completed_this_week"),
        F.lit(policy["policy_version"]).cast("string").alias("policy_version"),
    ).select(*REWARD_COLUMNS)

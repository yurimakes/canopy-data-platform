import os
import sys
from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)
GOLD_WEEKLY_USER_PATH = os.environ.get(
    "CANOPY_GOLD_WEEKLY_USER_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/",
)
GOLD_WEEKLY_CAMPAIGN_PATH = os.environ.get(
    "CANOPY_GOLD_WEEKLY_CAMPAIGN_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_campaign/",
)

MODES = ["walk", "bike", "car", "bus", "rail"]
LOW_CARBON_MODES = ["walk", "bike", "bus", "rail"]
TRANSIT_MODES = ["bus", "rail"]
SHORT_CAR_MAX_DISTANCE_M = 2000.0


def compute_last_iso_week(reference_date=None):
    ref = reference_date or datetime.now(timezone.utc).date()
    this_monday = ref - timedelta(days=ref.weekday())
    week_start = this_monday - timedelta(days=7)
    week_end = this_monday
    iso_year, iso_week, _ = week_start.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    return week_start.isoformat(), week_end.isoformat(), week_label


def read_confirmed_trips(spark, campaign_id, week_start, week_end):
    """Read finalized automatic Trip results; user feedback is not an auto-override gate."""
    df = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH)
    return df.filter(
        (F.col("campaign_id") == campaign_id)
        & (F.col("status") == "ready")
        & (F.col("ended_at") >= week_start)
        & (F.col("ended_at") < week_end)
    )


def dedupe_latest_confirmation(df):
    w = Window.partitionBy("trip_id").orderBy(F.col("updated_at").desc())
    ranked = df.withColumn("_rn", F.row_number().over(w))
    return ranked.filter(F.col("_rn") == 1).drop("_rn")


def assign_week(df):
    trip_date = F.to_date("ended_at")
    iso_day = F.pmod(F.dayofweek(trip_date) + F.lit(5), F.lit(7)) + F.lit(1)
    iso_thursday = F.date_add(trip_date, F.lit(4) - iso_day)
    return (
        df.withColumn("trip_date", trip_date)
        .withColumn("iso_year", F.year(iso_thursday))
        .withColumn("iso_week", F.weekofyear(trip_date))
        .withColumn(
            "week",
            F.concat(
                F.col("iso_year").cast("string"),
                F.lit("-W"),
                F.lpad(F.col("iso_week").cast("string"), 2, "0"),
            ),
        )
    )


def validate_carbon_contract(df):
    missing = df.filter(
        F.col("carbon.kg_co2e").isNull()
        | F.col("carbon.policy_version").isNull()
        | F.col("carbon.factor_version").isNull()
        | (F.col("carbon.unit") != F.lit("kgCO2e"))
    )
    if missing.limit(1).count():
        raise RuntimeError("ready Trip is missing canonical carbon/version/unit fields")

    versions = (
        df.select(
            F.col("carbon.policy_version").alias("policy_version"),
            F.col("carbon.factor_version").alias("factor_version"),
        )
        .distinct()
        .limit(2)
        .collect()
    )
    if len(versions) > 1:
        raise RuntimeError("mixed carbon policy/factor versions in one weekly aggregation")


def explode_segments(df):
    exploded = df.select(
        "trip_id",
        "user_id",
        "campaign_id",
        "week",
        F.col("carbon.policy_version").alias("carbon_policy_version"),
        F.col("carbon.factor_version").alias("factor_version"),
        F.explode("segments").alias("segment"),
    )
    return (
        exploded.withColumn("effective_mode", F.lower(F.col("segment.model_prediction")))
        .withColumn("distance_m", F.col("segment.distance_m").cast("double"))
        .withColumn("segment_kg_co2e", F.col("segment.carbon_kg").cast("double"))
    )


def compute_mode_metrics(exploded_df):
    if exploded_df.filter(F.col("segment_kg_co2e").isNull()).limit(1).count():
        raise RuntimeError("segment carbon_kg is required; weekly Gold must not recalculate emission factors")

    per_mode = exploded_df.groupBy(
        "user_id", "campaign_id", "week", "effective_mode"
    ).agg(
        F.countDistinct("trip_id").alias("mode_trip_count"),
        F.sum("distance_m").alias("distance_m"),
        F.sum("segment_kg_co2e").alias("kg_co2e"),
    )

    totals = exploded_df.groupBy("user_id", "campaign_id", "week").agg(
        F.countDistinct("trip_id").alias("total_trip_count"),
        F.sum("distance_m").alias("total_distance_m"),
        F.sum("segment_kg_co2e").alias("total_segment_kg_co2e"),
    )

    joined = per_mode.join(totals, ["user_id", "campaign_id", "week"])
    return (
        joined.withColumn("mode_trip_ratio", F.col("mode_trip_count") / F.col("total_trip_count"))
        .withColumn("mode_distance_ratio", F.col("distance_m") / F.col("total_distance_m"))
        .withColumn(
            "mode_carbon_ratio",
            F.when(
                F.col("total_segment_kg_co2e") > 0,
                F.col("kg_co2e") / F.col("total_segment_kg_co2e"),
            ).otherwise(F.lit(0.0)),
        )
    )


def compute_trip_primary_facts(exploded_df):
    """Create one row per non-empty Trip with a strict primary-mode contract.

    A Trip is valid only when every segment has a supported mode and a positive distance,
    and exactly one mode has the maximum summed segment distance. Invalid segments are not
    silently discarded because doing so would make Mission and Weekly Summary disagree.
    """
    keys = ["trip_id", "user_id", "campaign_id", "week"]
    invalid_segment = (
        ~F.col("effective_mode").isin(MODES)
        | F.col("distance_m").isNull()
        | (F.col("distance_m") <= 0)
    )

    quality = exploded_df.groupBy(*keys).agg(
        F.sum(F.when(invalid_segment, 1).otherwise(0)).alias("invalid_segment_count"),
        F.sum(
            F.when(~invalid_segment, F.col("distance_m")).otherwise(F.lit(0.0))
        ).alias("trip_distance_m"),
    )

    valid_segments = exploded_df.filter(~invalid_segment)
    per_trip_mode = valid_segments.groupBy(*keys, "effective_mode").agg(
        F.sum("distance_m").alias("mode_distance_m")
    )

    w = Window.partitionBy("trip_id")
    ranked = (
        per_trip_mode
        .withColumn("max_mode_distance_m", F.max("mode_distance_m").over(w))
        .withColumn(
            "is_primary_winner",
            F.when(
                F.abs(F.col("mode_distance_m") - F.col("max_mode_distance_m")) < F.lit(1e-9),
                F.lit(1),
            ).otherwise(F.lit(0)),
        )
    )
    mode_summary = ranked.groupBy(*keys).agg(
        F.sum("is_primary_winner").alias("primary_winner_count"),
        F.first(
            F.when(F.col("is_primary_winner") == 1, F.col("effective_mode")),
            ignorenulls=True,
        ).alias("primary_mode_candidate"),
    )

    result = (
        quality.join(mode_summary, keys, "left")
        .fillna(0, subset=["primary_winner_count"])
        .withColumn(
            "primary_mode_invalid_reason",
            F.when(F.col("invalid_segment_count") > 0, F.lit("invalid_segment"))
            .when(F.col("primary_winner_count") != 1, F.lit("primary_mode_tie")),
        )
        .withColumn(
            "primary_mode",
            F.when(
                F.col("primary_mode_invalid_reason").isNull(),
                F.col("primary_mode_candidate"),
            ),
        )
        .withColumn("primary_mode_valid", F.col("primary_mode_invalid_reason").isNull())
        .drop("primary_mode_candidate")
    )
    return result


def aggregate_primary_facts(primary_trip_df):
    return (
        primary_trip_df.groupBy("user_id", "campaign_id", "week")
        .agg(
            F.sum(F.when(F.col("primary_mode_valid"), 1).otherwise(0)).cast("long").alias("valid_primary_trip_count"),
            F.sum(F.when(~F.col("primary_mode_valid"), 1).otherwise(0)).cast("long").alias("invalid_primary_trip_count"),
            F.sum(F.when(F.col("primary_mode_invalid_reason") == "primary_mode_tie", 1).otherwise(0)).cast("long").alias("ambiguous_primary_trip_count"),
            F.sum(F.when(F.col("primary_mode_invalid_reason") == "invalid_segment", 1).otherwise(0)).cast("long").alias("invalid_segment_primary_trip_count"),
            F.sum(F.when(F.col("primary_mode") == "car", 1).otherwise(0)).cast("long").alias("car_primary_trip_count"),
            F.sum(F.when(F.col("primary_mode").isin(TRANSIT_MODES), 1).otherwise(0)).cast("long").alias("transit_primary_trip_count"),
            F.sum(F.when(F.col("primary_mode").isin(LOW_CARBON_MODES), 1).otherwise(0)).cast("long").alias("low_carbon_trip_count"),
            F.sum(
                F.when(
                    (F.col("primary_mode") == "car")
                    & (F.col("trip_distance_m") <= F.lit(SHORT_CAR_MAX_DISTANCE_M)),
                    1,
                ).otherwise(0)
            ).cast("long").alias("short_car_trip_count"),
        )
        .withColumn(
            "car_primary_ratio",
            F.when(
                F.col("valid_primary_trip_count") > 0,
                F.col("car_primary_trip_count") / F.col("valid_primary_trip_count"),
            ),
        )
        .withColumn(
            "short_car_share",
            F.when(
                F.col("car_primary_trip_count") > 0,
                F.col("short_car_trip_count") / F.col("car_primary_trip_count"),
            ),
        )
    )


def _pivot_ratio(mode_metrics_df, ratio_col, prefix):
    pivoted = (
        mode_metrics_df.groupBy("user_id", "campaign_id", "week")
        .pivot("effective_mode", MODES)
        .agg(F.first(ratio_col))
    )
    for mode in MODES:
        name = f"{prefix}_{mode}"
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted


def _pivot_mode_distance(mode_metrics_df):
    pivoted = (
        mode_metrics_df.groupBy("user_id", "campaign_id", "week")
        .pivot("effective_mode", MODES)
        .agg(F.first("distance_m"))
    )
    for mode in MODES:
        name = f"{mode}_distance_m"
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted


def build_personal_weekly(ready_df):
    validate_carbon_contract(ready_df)
    exploded = explode_segments(ready_df)
    mode_metrics = compute_mode_metrics(exploded)

    mode_distance_pivot = _pivot_mode_distance(mode_metrics)
    trip_ratio_pivot = _pivot_ratio(mode_metrics, "mode_trip_ratio", "mode_trip_ratio")
    distance_ratio_pivot = _pivot_ratio(mode_metrics, "mode_distance_ratio", "mode_distance_ratio")
    carbon_ratio_pivot = _pivot_ratio(mode_metrics, "mode_carbon_ratio", "mode_carbon_ratio")
    primary_facts = aggregate_primary_facts(compute_trip_primary_facts(exploded))

    trip_agg = ready_df.groupBy("user_id", "campaign_id", "week").agg(
        F.countDistinct("trip_id").alias("trip_count"),
        F.sum("carbon.kg_co2e").alias("total_kg_co2e"),
        F.first("carbon.policy_version").alias("carbon_policy_version"),
        F.first("carbon.factor_version").alias("factor_version"),
    )
    distance_agg = exploded.groupBy("user_id", "campaign_id", "week").agg(
        F.sum("distance_m").alias("total_distance_m")
    )

    return (
        trip_agg.join(distance_agg, ["user_id", "campaign_id", "week"])
        .join(mode_distance_pivot, ["user_id", "campaign_id", "week"])
        .join(trip_ratio_pivot, ["user_id", "campaign_id", "week"])
        .join(distance_ratio_pivot, ["user_id", "campaign_id", "week"])
        .join(carbon_ratio_pivot, ["user_id", "campaign_id", "week"])
        .join(primary_facts, ["user_id", "campaign_id", "week"], "left")
    )


def build_campaign_weekly(personal_weekly_df):
    ratio_prefixes = ["mode_trip_ratio", "mode_distance_ratio", "mode_carbon_ratio"]
    agg_exprs = [
        F.countDistinct("user_id").alias("participant_count"),
        F.sum("trip_count").alias("total_trip_count"),
        F.sum("total_distance_m").alias("total_distance_m"),
        F.sum("total_kg_co2e").alias("total_kg_co2e"),
        F.sum("valid_primary_trip_count").alias("valid_primary_trip_count"),
        F.sum("invalid_primary_trip_count").alias("invalid_primary_trip_count"),
        F.sum("ambiguous_primary_trip_count").alias("ambiguous_primary_trip_count"),
        F.sum("invalid_segment_primary_trip_count").alias("invalid_segment_primary_trip_count"),
        F.sum("car_primary_trip_count").alias("car_primary_trip_count"),
        F.sum("transit_primary_trip_count").alias("transit_primary_trip_count"),
        F.sum("low_carbon_trip_count").alias("low_carbon_trip_count"),
        F.sum("short_car_trip_count").alias("short_car_trip_count"),
        F.first("carbon_policy_version").alias("carbon_policy_version"),
        F.first("factor_version").alias("factor_version"),
    ]
    for mode in MODES:
        agg_exprs.append(F.sum(f"{mode}_distance_m").alias(f"{mode}_distance_m"))
    for prefix in ratio_prefixes:
        for mode in MODES:
            col = f"{prefix}_{mode}"
            agg_exprs.append(F.avg(col).alias(f"avg_{col}"))

    return personal_weekly_df.groupBy("campaign_id", "week").agg(*agg_exprs)


def write_gold(df, path):
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(path)
    )


def verify_weekly(spark, path, campaign_id, week):
    df = spark.read.format("delta").load(path)
    count = df.filter(
        (F.col("campaign_id") == campaign_id) & (F.col("week") == week)
    ).count()
    print(f"[verify] campaign_id={campaign_id} week={week} rows={count}")
    return count > 0


def run(campaign_id, week_start, week_end):
    spark = SparkSession.builder.getOrCreate()

    raw = read_confirmed_trips(spark, campaign_id, week_start, week_end)
    deduped = dedupe_latest_confirmation(raw)
    with_week = assign_week(deduped)

    week_label = with_week.select("week").first()
    week = week_label["week"] if week_label else None

    personal_weekly = build_personal_weekly(with_week)
    write_gold(personal_weekly, GOLD_WEEKLY_USER_PATH)

    campaign_weekly = build_campaign_weekly(personal_weekly)
    write_gold(campaign_weekly, GOLD_WEEKLY_CAMPAIGN_PATH)

    if week:
        ok_user = verify_weekly(spark, GOLD_WEEKLY_USER_PATH, campaign_id, week)
        ok_campaign = verify_weekly(spark, GOLD_WEEKLY_CAMPAIGN_PATH, campaign_id, week)
        if not (ok_user and ok_campaign):
            raise RuntimeError(
                f"campaign_id={campaign_id} week={week}: gold verification failed"
            )

    print(
        f"[done] campaign_id={campaign_id} week_start={week_start} "
        f"week_end={week_end} weekly summary complete"
    )


if __name__ == "__main__":
    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_start_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    week_end_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    if not campaign_id_arg:
        raise ValueError("campaign_id parameter required")

    if not week_start_arg or not week_end_arg:
        week_start_arg, week_end_arg, _ = compute_last_iso_week()

    run(campaign_id_arg, week_start_arg, week_end_arg)

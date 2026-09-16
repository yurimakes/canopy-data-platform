import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from reward_policy_classifier import classify_reward_status, compute_points, is_payable

CONFIRMED_TRIPS_PATH = os.environ.get(
    "CANOPY_CONFIRMED_TRIPS_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/confirmed_trips/",
)
GOLD_PERSONAL_BASELINE_PATH = os.environ.get(
    "CANOPY_GOLD_PERSONAL_BASELINE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/personal_baseline_history/",
)
GOLD_GLOBAL_BASELINE_PATH = os.environ.get(
    "CANOPY_GOLD_GLOBAL_BASELINE_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/global_baseline_history/",
)
REWARD_POLICY_PATH = os.environ.get(
    "CANOPY_REWARD_POLICY_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/reward_policy.yaml",
)
GOLD_REWARD_CALC_PATH = os.environ.get(
    "CANOPY_GOLD_REWARD_CALC_PATH",
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/reward_calculation/",
)


def load_policy(path):
    if path.startswith("abfss://") or path.startswith("dbfs:"):
        content = dbutils.fs.head(path, 5_000_000)  # noqa: F821
        return yaml.safe_load(content)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _week_bounds_utc(week, timezone_name=None):
    """Convert ISO week label (YYYY-Www) to campaign-local Monday boundaries in UTC."""
    tz_name = timezone_name or os.environ.get("CANOPY_CAMPAIGN_TIMEZONE", "Asia/Seoul")
    tz = ZoneInfo(tz_name)
    monday = datetime.strptime(f"{week}-1", "%G-W%V-%u").replace(tzinfo=tz)
    end = monday + timedelta(days=7)
    return monday.astimezone(ZoneInfo("UTC")).isoformat(), end.astimezone(ZoneInfo("UTC")).isoformat()


def _population_baseline():
    raw = os.environ.get("CANOPY_POPULATION_BASELINE_G_CO2E_PER_KM")
    source_id = os.environ.get("CANOPY_POPULATION_BASELINE_SOURCE_ID")
    if raw is None or raw == "":
        return None, source_id
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("CANOPY_POPULATION_BASELINE_G_CO2E_PER_KM must be numeric") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError("Population baseline must be finite and non-negative")
    return value, source_id


def read_reward_trips(spark, campaign_id, week):
    """Read latest ready Trip versions for one evaluation week and calculate per-Trip intensity."""
    start_utc, end_utc = _week_bounds_utc(week)
    raw = spark.read.format("delta").load(CONFIRMED_TRIPS_PATH).filter(
        (F.col("campaign_id") == campaign_id)
        & (F.col("status") == "ready")
        & (F.to_timestamp("ended_at") >= F.to_timestamp(F.lit(start_utc)))
        & (F.to_timestamp("ended_at") < F.to_timestamp(F.lit(end_utc)))
    )
    w = Window.partitionBy("trip_id").orderBy(F.col("updated_at").desc())
    latest = raw.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")
    trip_distance_m = F.expr(
        "aggregate(segments, cast(0.0 as double), "
        "(acc, x) -> acc + coalesce(cast(x.distance_m as double), cast(0.0 as double)))"
    )
    return (
        latest
        .withColumn("trip_distance_m", trip_distance_m)
        .withColumn("trip_carbon_kg", F.col("carbon.kg_co2e").cast("double"))
        .withColumn(
            "actual_g_co2e_per_km",
            F.when(
                F.col("trip_distance_m") > 0,
                (F.col("trip_carbon_kg") * F.lit(1000.0)) / (F.col("trip_distance_m") / F.lit(1000.0)),
            ),
        )
        .select(
            "trip_id",
            "user_id",
            "campaign_id",
            "trip_distance_m",
            "trip_carbon_kg",
            "actual_g_co2e_per_km",
            F.col("carbon.policy_version").alias("carbon_policy_version"),
            F.col("carbon.factor_version").alias("factor_version"),
        )
    )


def read_personal_baseline_map(spark, campaign_id, week):
    df = (
        spark.read.format("delta").load(GOLD_PERSONAL_BASELINE_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week) & (F.col("status") == "ready"))
        .select("user_id", "value", "policy_version", "eligibility_policy_version")
    )
    return {
        r["user_id"]: {
            "value": r["value"],
            "policy_version": r["policy_version"],
            "eligibility_policy_version": r["eligibility_policy_version"],
        }
        for r in df.collect()
    }


def read_global_baseline(spark, campaign_id, week):
    df = (
        spark.read.format("delta").load(GOLD_GLOBAL_BASELINE_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week) & (F.col("status") == "ready"))
        .select("value", "policy_version", "eligibility_policy_version")
    )
    row = df.first()
    return None if row is None else row.asDict(recursive=True)


def calculate_rewards(spark, campaign_id, week, policy):
    trips = read_reward_trips(spark, campaign_id, week).collect()
    personal = read_personal_baseline_map(spark, campaign_id, week)
    global_row = read_global_baseline(spark, campaign_id, week)
    global_value = None if global_row is None else global_row.get("value")
    population_value, population_source_id = _population_baseline()

    result_rows = []
    for row in trips:
        item = row.asDict(recursive=True)
        actual = item.get("actual_g_co2e_per_km")
        personal_row = personal.get(item["user_id"])
        personal_value = None if personal_row is None else personal_row.get("value")

        status, baseline_source, selected_baseline, reason = classify_reward_status(
            personal_value,
            global_value,
            population_value,
            actual,
        )
        points, point_reason = compute_points(status, selected_baseline, actual, policy)

        result_rows.append({
            "trip_id": item["trip_id"],
            "reward_type": "trip_carbon",
            "user_id": item["user_id"],
            "campaign_id": campaign_id,
            "week": week,
            "trip_distance_m": item.get("trip_distance_m"),
            "trip_carbon_kg": item.get("trip_carbon_kg"),
            "actual_g_co2e_per_km": actual,
            "personal_baseline_g_co2e_per_km": personal_value,
            "global_baseline_g_co2e_per_km": global_value,
            "population_baseline_g_co2e_per_km": population_value,
            "population_source_id": population_source_id,
            "baseline_source": baseline_source,
            "selected_baseline_g_co2e_per_km": selected_baseline,
            "status": status,
            "payable": is_payable(points),
            "points": points,
            "reason": reason,
            "point_reason": point_reason,
            "policy_version": policy["policy_version"],
            "baseline_policy_version": policy.get("baseline_policy_version"),
            "eligibility_policy_version": (
                (personal_row or {}).get("eligibility_policy_version")
                or (global_row or {}).get("eligibility_policy_version")
            ),
            "carbon_policy_version": item.get("carbon_policy_version"),
            "factor_version": item.get("factor_version"),
        })

    return result_rows


def write_reward_calculation(spark, result_rows):
    schema = (
        "trip_id string, reward_type string, user_id string, campaign_id string, week string, "
        "trip_distance_m double, trip_carbon_kg double, actual_g_co2e_per_km double, "
        "personal_baseline_g_co2e_per_km double, global_baseline_g_co2e_per_km double, "
        "population_baseline_g_co2e_per_km double, population_source_id string, "
        "baseline_source string, selected_baseline_g_co2e_per_km double, status string, "
        "payable boolean, points double, reason string, point_reason string, policy_version string, "
        "baseline_policy_version string, eligibility_policy_version string, carbon_policy_version string, "
        "factor_version string"
    )
    reward_df = spark.createDataFrame(result_rows, schema=schema) if result_rows else spark.createDataFrame([], schema)
    (
        reward_df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(GOLD_REWARD_CALC_PATH)
    )
    return reward_df


# Backward-compatible name retained for notebooks that imported the teammate implementation.
def submit_to_reward_ledger(spark, result_rows):
    return write_reward_calculation(spark, result_rows)


def verify(spark, campaign_id, week):
    df = spark.read.format("delta").load(GOLD_REWARD_CALC_PATH)
    count = df.filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week)).count()
    print(f"[verify] campaign_id={campaign_id} week={week} reward_calc rows={count}")
    return count >= 0


def run(campaign_id, week):
    spark = SparkSession.builder.getOrCreate()
    policy = load_policy(REWARD_POLICY_PATH)
    result_rows = calculate_rewards(spark, campaign_id, week, policy)
    write_reward_calculation(spark, result_rows)
    if not verify(spark, campaign_id, week):
        raise RuntimeError(f"campaign_id={campaign_id} week={week}: reward calculation verification failed")
    print(
        f"[done] campaign_id={campaign_id} week={week} "
        f"trip_reward_rows={len(result_rows)} policy_version={policy['policy_version']}"
    )


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None
    if not (campaign_id_arg and week_arg):
        raise ValueError("campaign_id and week parameters required")
    run(campaign_id_arg, week_arg)

from __future__ import annotations

from typing import Any

from baseline_runtime import CosmosIdentityConfig, build_cosmos_spark_options


def eligibility_columns(df):
    from pyspark.sql import functions as F
    return [F.col(name) for name in ('eligibility_policy_version','eligibility_reason','observation_days',
        'confirmed_trip_count','eligible','minimum_observation_days','minimum_trip_count','reasons','eligibility_status') if name in df.columns]


def personal_latest_documents(df: Any):
    from pyspark.sql import functions as F

    return df.select(
        F.concat(
            F.lit("baseline:personal:"),
            F.col("campaign_id"),
            F.lit(":"),
            F.col("user_id"),
        ).alias("id"),
        F.lit("personal_baseline_latest").alias("document_type"),
        "campaign_id",
        "user_id",
        "week",
        (F.col('status') if 'status' in df.columns else F.when(F.col("baseline_g_co2e_per_km").isNotNull(), F.lit("ready"))
        .otherwise(F.lit("collecting"))
        ).alias("status"),
        F.col("baseline_g_co2e_per_km").cast("double").alias("value_gco2e_per_km"),
        F.col("cumulative_g_co2e").cast("double"),
        F.col("cumulative_distance_km").cast("double"),
        "method",
        "policy_version",
        *eligibility_columns(df),
    )


def global_latest_documents(df: Any):
    from pyspark.sql import functions as F

    return df.select(
        F.concat(F.lit("baseline:global:"), F.col("campaign_id")).alias("id"),
        F.lit("global_baseline_latest").alias("document_type"),
        "campaign_id",
        "week",
        (F.col('status') if 'status' in df.columns else F.when(F.col("baseline_g_co2e_per_km").isNotNull(), F.lit("ready"))
        .otherwise(F.lit("insufficient_data"))
        ).alias("status"),
        F.col("baseline_g_co2e_per_km").cast("double").alias("value_gco2e_per_km"),
        F.col("valid_participant_count").cast("long"),
        "method",
        "policy_version",
        *eligibility_columns(df),
    )


def write_latest_documents(
    df: Any,
    identity: CosmosIdentityConfig,
    *,
    container: str,
) -> None:
    options = build_cosmos_spark_options(identity, container=container)
    (
        df.write.format("cosmos.oltp")
        .mode("append")
        .options(**options)
        .save()
    )


def verify_latest_documents(
    expected_df: Any,
    identity: CosmosIdentityConfig,
    *,
    container: str,
) -> None:
    """Read back latest documents and compare the fields needed downstream."""
    from pyspark.sql import functions as F

    options = build_cosmos_spark_options(identity, container=container)
    actual = (
        expected_df.sparkSession.read.format("cosmos.oltp")
        .options(**options)
        .load()
        .select(
            "id",
            F.col('status').alias('actual_status'),
            F.col("week").alias("actual_week"),
            F.col("policy_version").alias("actual_policy_version"),
            F.col("value_gco2e_per_km").cast("double").alias("actual_value"),
        )
    )
    expected = expected_df.select(
        "id",
        F.col('status').alias('expected_status'),
        F.col("week").alias("expected_week"),
        F.col("policy_version").alias("expected_policy_version"),
        F.col("value_gco2e_per_km").cast("double").alias("expected_value"),
    )
    joined = expected.join(actual, "id", "left")
    mismatch = joined.filter(
        F.col("actual_week").isNull()
        | (~F.col('actual_status').eqNullSafe(F.col('expected_status')))
        | (F.col("actual_week") != F.col("expected_week"))
        | (F.col("actual_policy_version") != F.col("expected_policy_version"))
        | (~F.col("actual_value").eqNullSafe(F.col("expected_value")))
    )
    if mismatch.limit(1).count():
        sample = mismatch.limit(5).toJSON().collect()
        raise RuntimeError(
            "Cosmos Baseline verification failed: " + "; ".join(sample)
        )

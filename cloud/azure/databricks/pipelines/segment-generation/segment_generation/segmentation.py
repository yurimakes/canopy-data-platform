"""Pure Spark transformations for finalized-trip mode segmentation."""

from __future__ import annotations

from typing import Any


def canonical_trip_ends(trip_ended: Any) -> Any:
    """Pick one non-conflicting lifecycle row per trip generation."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    keys = ["trip_id", "processing_generation"]
    logical_fields = [
        "user_id",
        "campaign_id",
        "started_at",
        "ended_at",
        "expected_last_sequence",
        "result_owner",
    ]

    variants = trip_ended.groupBy(*keys).agg(
        F.countDistinct(F.struct(*logical_fields)).alias("logical_variants")
    )
    ordered = Window.partitionBy(*keys).orderBy("occurred_at", "event_id")

    return (
        trip_ended.join(variants, keys, "inner")
        .withColumn("logical_rank", F.row_number().over(ordered))
        .where((F.col("logical_variants") == 1) & (F.col("logical_rank") == 1))
        .drop("logical_variants", "logical_rank")
    )


def canonical_predictions(predictions: Any) -> Any:
    """Keep the latest deterministic prediction for each event_id."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    ordered = Window.partitionBy("event_id").orderBy(
        F.col("predicted_at").desc_nulls_last(),
        F.col("model_version").desc_nulls_last(),
        F.col("predicted_mode").desc_nulls_last(),
    )
    return (
        predictions.withColumn("prediction_rank", F.row_number().over(ordered))
        .where(F.col("prediction_rank") == 1)
        .drop("prediction_rank")
    )


def build_ready_points(trip_ended: Any, gps: Any, predictions: Any) -> Any:
    """Return only complete trip generations with full prediction coverage."""
    from pyspark.sql import functions as F

    completions = canonical_trip_ends(
        trip_ended.where(F.col("result_owner") == "databricks")
    ).alias("c")
    gps = gps.alias("g")
    predictions = canonical_predictions(predictions).alias("p")

    points = (
        completions.join(
            gps,
            (F.col("c.trip_id") == F.col("g.trip_id"))
            & (F.col("g.sequence") <= F.col("c.expected_last_sequence")),
            "inner",
        )
        .join(predictions, F.col("g.event_id") == F.col("p.event_id"), "left")
        .select(
            F.col("c.trip_id").alias("trip_id"),
            F.col("c.processing_generation").alias("processing_generation"),
            F.col("c.expected_last_sequence").alias("expected_last_sequence"),
            F.col("c.parsed_at").alias("trip_end_parsed_at"),
            F.col("g.event_id").alias("event_id"),
            F.col("g.user_id").alias("user_id"),
            F.col("g.sequence").alias("sequence"),
            F.col("g.event_time").alias("event_time"),
            F.col("g.lat").alias("lat"),
            F.col("g.lon").alias("lon"),
            F.col("p.predicted_mode").alias("predicted_mode"),
            F.col("p.confidence").alias("point_confidence"),
            F.col("p.model_name").alias("model_name"),
            F.col("p.model_version").alias("model_version"),
            F.col("p.predicted_at").alias("predicted_at"),
        )
    )

    keys = ["trip_id", "processing_generation"]
    readiness = points.groupBy(*keys).agg(
        F.min("sequence").alias("observed_min_sequence"),
        F.max("sequence").alias("observed_max_sequence"),
        F.max("expected_last_sequence").alias("expected_last_sequence"),
        F.countDistinct("sequence").alias("distinct_sequences"),
        F.sum(F.when(F.col("predicted_mode").isNull(), 1).otherwise(0)).alias(
            "missing_predictions"
        ),
    )

    assessed = points.drop("expected_last_sequence").join(readiness, keys, "inner")

    return (
        assessed.where(
            (F.col("observed_max_sequence") == F.col("expected_last_sequence"))
            & (
                F.col("distinct_sequences")
                == (
                    F.col("observed_max_sequence")
                    - F.col("observed_min_sequence")
                    + F.lit(1)
                )
            )
            & (F.col("missing_predictions") == 0)
        )
        .drop(
            "observed_min_sequence",
            "observed_max_sequence",
            "expected_last_sequence",
            "distinct_sequences",
            "missing_predictions",
        )
    )


def stabilize_predictions(points: Any, max_gap_seconds: int) -> Any:
    """Repair transition-lag returns, then isolated one-point mode islands."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    if max_gap_seconds < 0:
        raise ValueError("max_gap_seconds must be non-negative")

    order = Window.partitionBy("trip_id", "processing_generation").orderBy(
        "sequence", "event_time", "event_id"
    )

    # Build independent window context in one projection. This preserves the
    # expressions while avoiding one Python/JVM logical-plan mutation per column.
    context = points.withColumns(
        {
            "m_lag2": F.lag("predicted_mode", 2).over(order),
            "m_lag1": F.lag("predicted_mode", 1).over(order),
            "m_lead1": F.lead("predicted_mode", 1).over(order),
            "t_lag2": F.lag("event_time", 2).over(order),
            "t_lag1": F.lag("event_time", 1).over(order),
            "t_lead1": F.lead("event_time", 1).over(order),
        }
    )

    gap_2_to_1 = F.unix_timestamp("t_lag1") - F.unix_timestamp("t_lag2")
    gap_1_to_0 = F.unix_timestamp("event_time") - F.unix_timestamp("t_lag1")
    gap_0_to_1 = F.unix_timestamp("t_lead1") - F.unix_timestamp("event_time")

    transition_lag = (
        (F.col("m_lag2") == F.col("predicted_mode"))
        & (F.col("m_lag1") == F.col("m_lead1"))
        & (F.col("m_lag1") != F.col("predicted_mode"))
        & gap_2_to_1.between(0, max_gap_seconds)
        & gap_1_to_0.between(0, max_gap_seconds)
        & gap_0_to_1.between(0, max_gap_seconds)
    )

    repaired = context.withColumn(
        "transition_mode",
        F.when(transition_lag, F.col("m_lag1")).otherwise(F.col("predicted_mode")),
    )

    repaired = repaired.withColumns(
        {
            "r_lag1": F.lag("transition_mode", 1).over(order),
            "r_lead1": F.lead("transition_mode", 1).over(order),
            "r_t_lag1": F.lag("event_time", 1).over(order),
            "r_t_lead1": F.lead("event_time", 1).over(order),
        }
    )
    left_gap = F.unix_timestamp("event_time") - F.unix_timestamp("r_t_lag1")
    right_gap = F.unix_timestamp("r_t_lead1") - F.unix_timestamp("event_time")

    isolated = (
        (F.col("r_lag1") == F.col("r_lead1"))
        & (F.col("transition_mode") != F.col("r_lag1"))
        & left_gap.between(0, max_gap_seconds)
        & right_gap.between(0, max_gap_seconds)
    )

    return repaired.withColumn(
        "stabilized_mode",
        F.when(isolated, F.col("r_lag1")).otherwise(F.col("transition_mode")),
    ).drop(
        "m_lag2",
        "m_lag1",
        "m_lead1",
        "t_lag2",
        "t_lag1",
        "t_lead1",
        "transition_mode",
        "r_lag1",
        "r_lead1",
        "r_t_lag1",
        "r_t_lead1",
    )


def build_segments(points: Any) -> Any:
    """Collapse stabilized point predictions into deterministic mode segments."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    order = Window.partitionBy("trip_id", "processing_generation").orderBy(
        "sequence", "event_time", "event_id"
    )
    running = order.rowsBetween(Window.unboundedPreceding, Window.currentRow)

    # Materialize shared lag expressions once. The original implementation
    # embedded the same mode lag in multiple downstream expressions.
    marked = points.withColumns(
        {
            "_previous_mode": F.lag("stabilized_mode").over(order),
            "_previous_lat": F.lag("lat").over(order),
            "_previous_lon": F.lag("lon").over(order),
        }
    )
    marked = marked.withColumn(
        "segment_start",
        F.when(
            F.col("_previous_mode").isNull()
            | (F.col("_previous_mode") != F.col("stabilized_mode")),
            1,
        ).otherwise(0),
    ).withColumn("segment_index", F.sum("segment_start").over(running))

    lat1 = F.radians("_previous_lat")
    lat2 = F.radians("lat")
    delta_lat = lat2 - lat1
    delta_lon = F.radians(F.col("lon") - F.col("_previous_lon"))
    haversine_a = (
        F.pow(F.sin(delta_lat / 2.0), 2)
        + F.cos(lat1) * F.cos(lat2) * F.pow(F.sin(delta_lon / 2.0), 2)
    )
    edge_m = (
        2.0
        * F.lit(6_371_008.8)
        * F.asin(F.sqrt(F.least(F.lit(1.0), haversine_a)))
    )

    marked = marked.withColumn(
        "internal_edge_m",
        F.when(
            F.col("_previous_mode") == F.col("stabilized_mode"),
            edge_m,
        ).otherwise(F.lit(0.0)),
    )

    marked = marked.drop("_previous_mode", "_previous_lat", "_previous_lon")

    grain = ["trip_id", "processing_generation", "segment_index"]
    return (
        marked.groupBy(*grain)
        .agg(
            F.first("user_id", ignorenulls=True).alias("user_id"),
            F.first("stabilized_mode", ignorenulls=True).alias("mode"),
            F.min("sequence").alias("start_sequence"),
            F.max("sequence").alias("end_sequence"),
            F.min_by(
                "event_time", F.struct("sequence", "event_time", "event_id")
            ).alias("start_time"),
            F.max_by(
                "event_time", F.struct("sequence", "event_time", "event_id")
            ).alias("end_time"),
            F.sum("internal_edge_m").cast("double").alias("distance_m"),
            F.lit(None).cast("double").alias("confidence"),
            F.min("model_name").alias("model_name"),
            F.min("model_version").alias("model_version"),
            F.max("predicted_at").alias("latest_prediction_at"),
            F.max("trip_end_parsed_at").alias("trip_end_parsed_at"),
            F.count(F.lit(1)).cast("long").alias("point_count"),
        )
        .withColumn(
            "segment_id",
            F.concat(
                "trip_id",
                F.lit(":g"),
                F.col("processing_generation"),
                F.lit(":segment:"),
                F.col("segment_index"),
            ),
        )
        .withColumn("segmentation_version", F.lit("time-segmentation-v1"))
        .withColumn("segmented_at", F.current_timestamp())
        .select(
            "trip_id",
            "user_id",
            "processing_generation",
            F.col("segment_index").cast("int").alias("segment_index"),
            "segment_id",
            "mode",
            "start_sequence",
            "end_sequence",
            "start_time",
            "end_time",
            "point_count",
            "distance_m",
            "confidence",
            "model_name",
            "model_version",
            "latest_prediction_at",
            "trip_end_parsed_at",
            "segmentation_version",
            "segmented_at",
        )
    )

"""Low-latency replay finalizer driven by trip-end and prediction changes."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession, functions as F

from segment_generation.segmentation import (
    build_ready_points,
    build_segments,
    stabilize_predictions,
)


def _spark() -> SparkSession:
    session = SparkSession.getActiveSession()
    if session is None:
        raise RuntimeError("Lakeflow pipeline requires an active SparkSession")
    return session


def _conf(name: str) -> str:
    value = _spark().conf.get(f"canopy.{name}")
    if not value or not value.strip():
        raise ValueError(f"missing Lakeflow pipeline configuration: canopy.{name}")
    return value.strip()


CATALOG = _conf("catalog")
SCHEMA = _conf("schema")
TRIP_ENDED_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('trip_ended_table')}"
GPS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('gps_observations_table')}"
PREDICTIONS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('mode_predictions_table')}"
SEGMENTS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('segments_table')}"
MAX_REPAIR_GAP_SECONDS = int(_conf("max_repair_gap_seconds"))


def _finalize_affected_trips(trigger_batch: DataFrame, batch_id: int) -> None:
    spark = trigger_batch.sparkSession
    affected = (
        trigger_batch.where(F.col("trip_id").isNotNull())
        .select("trip_id")
        .distinct()
        .cache()
    )
    try:
        if affected.limit(1).count() == 0:
            return

        trip_ended = spark.table(TRIP_ENDED_TABLE).join(affected, "trip_id", "semi")
        gps = spark.table(GPS_TABLE).join(affected, "trip_id", "semi")
        predictions = spark.table(PREDICTIONS_TABLE).join(affected, "trip_id", "semi")

        ready = build_ready_points(trip_ended, gps, predictions)
        stabilized = stabilize_predictions(ready, MAX_REPAIR_GAP_SECONDS)
        segments = build_segments(stabilized)

        if segments.limit(1).count() == 0:
            return

        temp_view = f"_ready_segments_{batch_id}"
        segments.createOrReplaceTempView(temp_view)
        spark.sql(
            f"""
            MERGE INTO {SEGMENTS_TABLE} AS target
            USING {temp_view} AS source
              ON target.segment_id = source.segment_id
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
    finally:
        affected.unpersist()


@dp.foreach_batch_sink(name="low_latency_segment_sink")
def low_latency_segment_sink(df: DataFrame, batch_id: int) -> None:
    _finalize_affected_trips(df, batch_id)


@dp.append_flow(
    target="low_latency_segment_sink",
    name="trip_end_finalization_trigger",
)
def trip_end_finalization_trigger() -> DataFrame:
    return _spark().readStream.table(TRIP_ENDED_TABLE).select("trip_id")


@dp.append_flow(
    target="low_latency_segment_sink",
    name="prediction_finalization_trigger",
)
def prediction_finalization_trigger() -> DataFrame:
    return _spark().readStream.table(PREDICTIONS_TABLE).select("trip_id")

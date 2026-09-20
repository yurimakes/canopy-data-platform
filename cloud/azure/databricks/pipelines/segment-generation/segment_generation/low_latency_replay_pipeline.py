"""Low-latency replay finalizer driven by trip-end and prediction changes."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession, functions as F, types as T

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


CATALOG = _conf("catalog")
SCHEMA = _conf("schema")
TRIP_ENDED_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('trip_ended_table')}"
GPS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('gps_observations_table')}"
PREDICTIONS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('mode_predictions_table')}"
SEGMENTS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('segments_table')}"
TELEMETRY_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('telemetry_table')}"
MAX_REPAIR_GAP_SECONDS = int(_conf("max_repair_gap_seconds"))

_TELEMETRY_SCHEMA = T.StructType(
    [
        T.StructField("batch_id", T.LongType(), False),
        T.StructField("affected_trip_ids", T.ArrayType(T.StringType(), False), False),
        T.StructField("batch_entered_at", T.TimestampType(), False),
        T.StructField("affected_probe_started_at", T.TimestampType(), False),
        T.StructField("affected_probe_finished_at", T.TimestampType(), False),
        T.StructField("segment_probe_started_at", T.TimestampType(), True),
        T.StructField("segment_probe_finished_at", T.TimestampType(), True),
        T.StructField("merge_started_at", T.TimestampType(), True),
        T.StructField("merge_finished_at", T.TimestampType(), True),
        T.StructField("batch_finished_at", T.TimestampType(), False),
        T.StructField("affected_present", T.BooleanType(), False),
        T.StructField("segments_ready", T.BooleanType(), True),
        T.StructField("affected_probe_ms", T.DoubleType(), False),
        T.StructField("trip_end_probe_ms", T.DoubleType(), True),
        T.StructField("pending_probe_ms", T.DoubleType(), True),
        T.StructField("pending_projection_ms", T.DoubleType(), True),
        T.StructField("gps_plan_ms", T.DoubleType(), True),
        T.StructField("predictions_plan_ms", T.DoubleType(), True),
        T.StructField("ready_plan_ms", T.DoubleType(), True),
        T.StructField("stabilize_plan_ms", T.DoubleType(), True),
        T.StructField("segments_plan_ms", T.DoubleType(), True),
        T.StructField("segment_boundary_plan_ms", T.DoubleType(), True),
        T.StructField("segment_distance_plan_ms", T.DoubleType(), True),
        T.StructField("segment_aggregate_plan_ms", T.DoubleType(), True),
        T.StructField("segment_output_plan_ms", T.DoubleType(), True),
        T.StructField("build_segments_transform_ms", T.DoubleType(), True),
        T.StructField("segments_cache_registration_ms", T.DoubleType(), True),
        T.StructField("pre_segment_plan_ms", T.DoubleType(), True),
        T.StructField("segment_probe_ms", T.DoubleType(), True),
        T.StructField("merge_ms", T.DoubleType(), True),
        T.StructField("batch_total_ms", T.DoubleType(), False),
        T.StructField("status", T.StringType(), False),
    ]
)


def _write_telemetry(spark: SparkSession, row: dict[str, object]) -> None:
    (
        spark.createDataFrame([row], schema=_TELEMETRY_SCHEMA)
        .write.format("delta")
        .option("mergeSchema", "true")
        .mode("append")
        .saveAsTable(TELEMETRY_TABLE)
    )


def _finalize_affected_trips(trigger_batch: DataFrame, batch_id: int) -> None:
    spark = trigger_batch.sparkSession
    batch_entered_at = _utc_now()
    batch_started = time.perf_counter()

    affected = (
        trigger_batch.where(F.col("trip_id").isNotNull())
        .select("trip_id")
        .distinct()
        .cache()
    )

    affected_probe_started_at = _utc_now()
    affected_probe_started = time.perf_counter()
    affected_trip_ids = [row["trip_id"] for row in affected.select("trip_id").collect()]
    affected_present = len(affected_trip_ids) > 0
    affected_probe_finished_at = _utc_now()
    affected_probe_ms = (time.perf_counter() - affected_probe_started) * 1000.0

    segment_probe_started_at = None
    segment_probe_finished_at = None
    trip_end_probe_ms = None
    pending_probe_ms = None
    pending_projection_ms = None
    gps_plan_ms = None
    predictions_plan_ms = None
    ready_plan_ms = None
    stabilize_plan_ms = None
    segments_plan_ms = None
    segment_boundary_plan_ms = None
    segment_distance_plan_ms = None
    segment_aggregate_plan_ms = None
    segment_output_plan_ms = None
    build_segments_transform_ms = None
    segments_cache_registration_ms = None
    pre_segment_plan_ms = None
    merge_started_at = None
    merge_finished_at = None
    segment_probe_ms = None
    merge_ms = None
    segments_ready = None
    status = "no_affected_trips"

    trip_ended = None
    pending_trip_ended = None
    segments = None
    try:
        if affected_present:
            # Prediction batches arrive throughout an active trip, but finalized-trip
            # segmentation cannot succeed until a trip_ended row exists. Probe that
            # cheap prerequisite first so pre-trip-end batches do not execute the
            # full GPS/prediction/window plan.
            trip_ended = (
                spark.table(TRIP_ENDED_TABLE)
                .join(affected, "trip_id", "semi")
                .cache()
            )
            trip_end_probe_started = time.perf_counter()
            has_trip_end = trip_ended.limit(1).count() > 0
            trip_end_probe_ms = (
                time.perf_counter() - trip_end_probe_started
            ) * 1000.0

            if not has_trip_end:
                status = "no_trip_end"
            else:
                finalized_generations = (
                    spark.table(SEGMENTS_TABLE)
                    .select("trip_id", "processing_generation")
                    .distinct()
                )
                pending_trip_ended = (
                    trip_ended.alias("t")
                    .join(
                        finalized_generations.alias("f"),
                        (F.col("t.trip_id") == F.col("f.trip_id"))
                        & (
                            F.col("t.processing_generation")
                            == F.col("f.processing_generation")
                        ),
                        "left_anti",
                    )
                    .cache()
                )
                pending_probe_started = time.perf_counter()
                has_pending_generation = pending_trip_ended.limit(1).count() > 0
                pending_probe_ms = (
                    time.perf_counter() - pending_probe_started
                ) * 1000.0

                if not has_pending_generation:
                    status = "already_finalized"
                else:
                    pre_segment_plan_started = time.perf_counter()

                    stage_started = time.perf_counter()
                    pending_affected = pending_trip_ended.select("trip_id").distinct()
                    pending_projection_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0

                    stage_started = time.perf_counter()
                    gps = spark.table(GPS_TABLE).join(
                        pending_affected, "trip_id", "semi"
                    )
                    gps_plan_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0

                    stage_started = time.perf_counter()
                    predictions = spark.table(PREDICTIONS_TABLE).join(
                        pending_affected, "trip_id", "semi"
                    )
                    predictions_plan_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0

                    stage_started = time.perf_counter()
                    ready = build_ready_points(
                        pending_trip_ended, gps, predictions
                    )
                    ready_plan_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0

                    stage_started = time.perf_counter()
                    stabilized = stabilize_predictions(
                        ready, MAX_REPAIR_GAP_SECONDS
                    )
                    stabilize_plan_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0

                    stage_started = time.perf_counter()
                    segment_plan_timings: dict[str, float] = {}

                    build_segments_started = time.perf_counter()
                    segment_rows = build_segments(
                        stabilized, plan_timings=segment_plan_timings
                    )
                    build_segments_transform_ms = (
                        time.perf_counter() - build_segments_started
                    ) * 1000.0

                    # Cache registration is intentionally measured separately
                    # from the pure transformation-plan construction.
                    cache_registration_started = time.perf_counter()
                    segments = segment_rows.cache()
                    segments_cache_registration_ms = (
                        time.perf_counter() - cache_registration_started
                    ) * 1000.0

                    segments_plan_ms = (
                        time.perf_counter() - stage_started
                    ) * 1000.0
                    segment_boundary_plan_ms = segment_plan_timings.get(
                        "segment_boundary_plan_ms"
                    )
                    segment_distance_plan_ms = segment_plan_timings.get(
                        "segment_distance_plan_ms"
                    )
                    segment_aggregate_plan_ms = segment_plan_timings.get(
                        "segment_aggregate_plan_ms"
                    )
                    segment_output_plan_ms = segment_plan_timings.get(
                        "segment_output_plan_ms"
                    )

                    pre_segment_plan_ms = (
                        time.perf_counter() - pre_segment_plan_started
                    ) * 1000.0

                    segment_probe_started_at = _utc_now()
                    segment_probe_started = time.perf_counter()
                    segments_ready = segments.limit(1).count() > 0
                    segment_probe_finished_at = _utc_now()
                    segment_probe_ms = (
                        time.perf_counter() - segment_probe_started
                    ) * 1000.0

                    if segments_ready:
                        merge_started_at = _utc_now()
                        merge_started = time.perf_counter()
                        (
                            segments.write.format("delta")
                            .mode("append")
                            .saveAsTable(SEGMENTS_TABLE)
                        )
                        merge_finished_at = _utc_now()
                        merge_ms = (
                            time.perf_counter() - merge_started
                        ) * 1000.0
                        status = "appended"
                    else:
                        status = "not_ready"

        batch_finished_at = _utc_now()
        batch_total_ms = (time.perf_counter() - batch_started) * 1000.0
        _write_telemetry(
            spark,
            {
                "batch_id": int(batch_id),
                "affected_trip_ids": affected_trip_ids,
                "batch_entered_at": batch_entered_at,
                "affected_probe_started_at": affected_probe_started_at,
                "affected_probe_finished_at": affected_probe_finished_at,
                "segment_probe_started_at": segment_probe_started_at,
                "segment_probe_finished_at": segment_probe_finished_at,
                "merge_started_at": merge_started_at,
                "merge_finished_at": merge_finished_at,
                "batch_finished_at": batch_finished_at,
                "affected_present": bool(affected_present),
                "segments_ready": segments_ready,
                "affected_probe_ms": float(affected_probe_ms),
                "trip_end_probe_ms": trip_end_probe_ms,
                "pending_probe_ms": pending_probe_ms,
                "pending_projection_ms": pending_projection_ms,
                "gps_plan_ms": gps_plan_ms,
                "predictions_plan_ms": predictions_plan_ms,
                "ready_plan_ms": ready_plan_ms,
                "stabilize_plan_ms": stabilize_plan_ms,
                "segments_plan_ms": segments_plan_ms,
                "segment_boundary_plan_ms": segment_boundary_plan_ms,
                "segment_distance_plan_ms": segment_distance_plan_ms,
                "segment_aggregate_plan_ms": segment_aggregate_plan_ms,
                "segment_output_plan_ms": segment_output_plan_ms,
                "build_segments_transform_ms": build_segments_transform_ms,
                "segments_cache_registration_ms": segments_cache_registration_ms,
                "pre_segment_plan_ms": pre_segment_plan_ms,
                "segment_probe_ms": segment_probe_ms,
                "merge_ms": merge_ms,
                "batch_total_ms": float(batch_total_ms),
                "status": status,
            },
        )
    finally:
        if segments is not None:
            segments.unpersist()
        if pending_trip_ended is not None:
            pending_trip_ended.unpersist()
        if trip_ended is not None:
            trip_ended.unpersist()
        affected.unpersist()


@dp.foreach_batch_sink(name="low_latency_segment_sink")
def low_latency_segment_sink(df: DataFrame, batch_id: int) -> None:
    _finalize_affected_trips(df, batch_id)


@dp.append_flow(
    target="low_latency_segment_sink",
    name="segment_finalization_trigger",
)
def segment_finalization_trigger() -> DataFrame:
    trip_ends = _spark().readStream.table(TRIP_ENDED_TABLE).select("trip_id")
    predictions = _spark().readStream.table(PREDICTIONS_TABLE).select("trip_id")
    return trip_ends.unionByName(predictions)

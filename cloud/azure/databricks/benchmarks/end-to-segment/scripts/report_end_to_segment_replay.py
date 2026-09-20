"""Wait for replay segments and report trip-end-to-segment latency."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F, types as T


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--prediction-table", required=True)
    p.add_argument("--arrival-table", required=True)
    p.add_argument("--segments-table", required=True)
    p.add_argument("--segment-telemetry-table", required=True)
    p.add_argument("--benchmark-table", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--users", type=int, required=True)
    p.add_argument("--timeout-seconds", type=int, default=180)
    p.add_argument("--poll-seconds", type=float, default=1.0)
    return p.parse_args()


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    predictions_name = f"{args.catalog}.{args.schema}.{args.prediction_table}"
    arrivals_name = f"{args.catalog}.{args.schema}.{args.arrival_table}"
    segments_name = f"{args.catalog}.{args.schema}.{args.segments_table}"
    telemetry_name = f"{args.catalog}.{args.schema}.{args.segment_telemetry_table}"
    benchmark_name = f"{args.catalog}.{args.schema}.{args.benchmark_table}"
    prefix = f"replay:{args.run_id}:trip:"

    deadline = time.monotonic() + args.timeout_seconds
    first_visible_at: dict[str, datetime] = {}
    segmented_trips = 0
    while time.monotonic() < deadline:
        visible_trip_ids = [
            row["trip_id"]
            for row in (
                spark.table(segments_name)
                .where(F.col("trip_id").startswith(prefix))
                .select("trip_id")
                .distinct()
                .collect()
            )
        ]
        observed_at = now_utc_naive()
        for trip_id in visible_trip_ids:
            first_visible_at.setdefault(trip_id, observed_at)
        segmented_trips = len(first_visible_at)
        if segmented_trips >= args.users:
            break
        print("SEGMENT_WAIT", {"segmented_trips": segmented_trips, "expected": args.users})
        time.sleep(args.poll_seconds)

    if segmented_trips < args.users:
        raise TimeoutError(
            f"timed out with {segmented_trips}/{args.users} segmented trips for {args.run_id}"
        )

    trip_ends = (
        spark.table(trip_end_name)
        .where(F.col("trip_id").startswith(prefix))
        .select("trip_id", "parsed_at", "expected_last_sequence")
    )
    prediction_rows = (
        spark.table(predictions_name)
        .where(F.col("trip_id").startswith(prefix))
        .select(
            "event_id",
            "trip_id",
            "sequence",
            "features_processed_at",
            "predicted_at",
        )
    )
    predictions = (
        prediction_rows.groupBy("trip_id")
        .agg(
            F.max("sequence").alias("max_predicted_sequence"),
            F.max("predicted_at").alias("last_predicted_at"),
        )
    )
    segments = (
        spark.table(segments_name)
        .where(F.col("trip_id").startswith(prefix))
        .groupBy("trip_id")
        .agg(
            F.max("segmented_at").alias("segmented_at"),
            F.sum("point_count").alias("segment_point_coverage"),
            F.count("*").alias("segment_count"),
        )
    )
    visibility = spark.createDataFrame(
        [(trip_id, observed_at) for trip_id, observed_at in first_visible_at.items()],
        "trip_id string, segments_visible_at timestamp",
    )

    per_trip = (
        trip_ends.join(predictions, "trip_id", "inner")
        .join(segments, "trip_id", "inner")
        .join(visibility, "trip_id", "inner")
        .withColumn(
            "trip_end_to_prediction_ms",
            (F.col("last_predicted_at").cast("double") - F.col("parsed_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "prediction_to_segments_ms",
            (F.col("segments_visible_at").cast("double") - F.col("last_predicted_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "trip_end_to_segments_ms",
            (F.col("segments_visible_at").cast("double") - F.col("parsed_at").cast("double")) * 1000.0,
        )
    )

    arrivals = (
        spark.table(arrivals_name)
        .where(F.col("run_id") == args.run_id)
        .select("event_id", "trip_id", "sequence", "replay_visible_at")
    )

    stage_rows = (
        arrivals.alias("a")
        .join(
            prediction_rows.alias("p"),
            F.col("a.event_id") == F.col("p.event_id"),
            "inner",
        )
        .select(
            F.col("a.trip_id").alias("trip_id"),
            F.col("a.sequence").alias("sequence"),
            F.col("a.replay_visible_at").alias("replay_visible_at"),
            F.col("p.features_processed_at").alias("features_processed_at"),
            F.col("p.predicted_at").alias("predicted_at"),
        )
        .withColumn(
            "visible_to_features_ms",
            (F.col("features_processed_at").cast("double") - F.col("replay_visible_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "features_to_prediction_ms",
            (F.col("predicted_at").cast("double") - F.col("features_processed_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "visible_to_prediction_ms",
            (F.col("predicted_at").cast("double") - F.col("replay_visible_at").cast("double")) * 1000.0,
        )
    )

    stage_summary = stage_rows.agg(
        F.count("*").alias("rows"),
        F.avg("visible_to_features_ms").alias("avg_visible_to_features_ms"),
        F.expr("percentile_approx(visible_to_features_ms, 0.50)").alias("p50_visible_to_features_ms"),
        F.expr("percentile_approx(visible_to_features_ms, 0.95)").alias("p95_visible_to_features_ms"),
        F.max("visible_to_features_ms").alias("max_visible_to_features_ms"),
        F.avg("features_to_prediction_ms").alias("avg_features_to_prediction_ms"),
        F.expr("percentile_approx(features_to_prediction_ms, 0.50)").alias("p50_features_to_prediction_ms"),
        F.expr("percentile_approx(features_to_prediction_ms, 0.95)").alias("p95_features_to_prediction_ms"),
        F.max("features_to_prediction_ms").alias("max_features_to_prediction_ms"),
        F.avg("visible_to_prediction_ms").alias("avg_visible_to_prediction_ms"),
        F.expr("percentile_approx(visible_to_prediction_ms, 0.50)").alias("p50_visible_to_prediction_ms"),
        F.expr("percentile_approx(visible_to_prediction_ms, 0.95)").alias("p95_visible_to_prediction_ms"),
        F.max("visible_to_prediction_ms").alias("max_visible_to_prediction_ms"),
    ).collect()[0]

    final_sequence_stage = (
        stage_rows.alias("s")
        .join(
            trip_ends.select(
                "trip_id",
                F.col("expected_last_sequence").alias("final_sequence"),
            ).alias("t"),
            (F.col("s.trip_id") == F.col("t.trip_id"))
            & (F.col("s.sequence") == F.col("t.final_sequence")),
            "inner",
        )
        .select(
            F.col("s.trip_id").alias("trip_id"),
            "replay_visible_at",
            "features_processed_at",
            "predicted_at",
            "visible_to_features_ms",
            "features_to_prediction_ms",
            "visible_to_prediction_ms",
        )
        .collect()
    )

    print("INFERENCE_STAGE_REPORT", {
        "run_id": args.run_id,
        "all_prediction_rows": {
            name: (float(stage_summary[name]) if stage_summary[name] is not None and name != "rows" else int(stage_summary[name]))
            for name in stage_summary.__fields__
        },
        "final_sequence_per_trip": {
            r["trip_id"]: {
                "replay_visible_at": str(r["replay_visible_at"]),
                "features_processed_at": str(r["features_processed_at"]),
                "predicted_at": str(r["predicted_at"]),
                "visible_to_features_ms": float(r["visible_to_features_ms"]),
                "features_to_prediction_ms": float(r["features_to_prediction_ms"]),
                "visible_to_prediction_ms": float(r["visible_to_prediction_ms"]),
            }
            for r in final_sequence_stage
        },
    })


    telemetry_deadline = time.monotonic() + min(args.timeout_seconds, 30)
    telemetry_rows = []
    while time.monotonic() < telemetry_deadline:
        telemetry_rows = (
            spark.table(telemetry_name)
            .where(
                F.exists(
                    F.col("affected_trip_ids"),
                    lambda trip_id: trip_id.startswith(prefix),
                )
            )
            .orderBy("batch_id")
            .collect()
        )
        if any(r["status"] in ("appended", "merged") for r in telemetry_rows):
            break
        time.sleep(args.poll_seconds)
    print(
        "SEGMENT_STAGE_REPORT",
        {
            "run_id": args.run_id,
            "batches": [
                {
                    "batch_id": int(r["batch_id"]),
                    "affected_trip_ids": list(r["affected_trip_ids"]),
                    "status": r["status"],
                    "affected_probe_ms": float(r["affected_probe_ms"]),
                    "trip_end_probe_ms": (
                        float(r["trip_end_probe_ms"])
                        if r["trip_end_probe_ms"] is not None
                        else None
                    ),
                    "pending_probe_ms": (
                        float(r["pending_probe_ms"])
                        if r["pending_probe_ms"] is not None
                        else None
                    ),
                    "pending_projection_ms": (
                        float(r["pending_projection_ms"])
                        if r["pending_projection_ms"] is not None
                        else None
                    ),
                    "gps_plan_ms": (
                        float(r["gps_plan_ms"])
                        if r["gps_plan_ms"] is not None
                        else None
                    ),
                    "predictions_plan_ms": (
                        float(r["predictions_plan_ms"])
                        if r["predictions_plan_ms"] is not None
                        else None
                    ),
                    "ready_plan_ms": (
                        float(r["ready_plan_ms"])
                        if r["ready_plan_ms"] is not None
                        else None
                    ),
                    "stabilize_plan_ms": (
                        float(r["stabilize_plan_ms"])
                        if r["stabilize_plan_ms"] is not None
                        else None
                    ),
                    "segments_plan_ms": (
                        float(r["segments_plan_ms"])
                        if r["segments_plan_ms"] is not None
                        else None
                    ),
                    "pre_segment_plan_ms": (
                        float(r["pre_segment_plan_ms"])
                        if r["pre_segment_plan_ms"] is not None
                        else None
                    ),
                    "segment_probe_ms": (
                        float(r["segment_probe_ms"])
                        if r["segment_probe_ms"] is not None
                        else None
                    ),
                    "merge_ms": float(r["merge_ms"]) if r["merge_ms"] is not None else None,
                    "batch_total_ms": float(r["batch_total_ms"]),
                    "batch_entered_at": str(r["batch_entered_at"]),
                    "segment_probe_started_at": str(r["segment_probe_started_at"]),
                    "segment_probe_finished_at": str(r["segment_probe_finished_at"]),
                    "merge_started_at": str(r["merge_started_at"]),
                    "merge_finished_at": str(r["merge_finished_at"]),
                    "batch_finished_at": str(r["batch_finished_at"]),
                }
                for r in telemetry_rows
            ],
        },
    )

    rows = per_trip.collect()
    if len(rows) != args.users:
        raise ValueError(f"expected {args.users} completed trips but found {len(rows)}")

    def vals(name: str) -> list[float]:
        return [float(r[name]) for r in rows]

    end_to_pred = vals("trip_end_to_prediction_ms")
    pred_to_seg = vals("prediction_to_segments_ms")
    end_to_seg = vals("trip_end_to_segments_ms")

    summary = [{
        "run_id": args.run_id,
        "users": args.users,
        "avg_trip_end_to_prediction_ms": sum(end_to_pred) / len(end_to_pred),
        "max_trip_end_to_prediction_ms": max(end_to_pred),
        "avg_prediction_to_segments_ms": sum(pred_to_seg) / len(pred_to_seg),
        "max_prediction_to_segments_ms": max(pred_to_seg),
        "avg_trip_end_to_segments_ms": sum(end_to_seg) / len(end_to_seg),
        "max_trip_end_to_segments_ms": max(end_to_seg),
        "reported_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }]

    schema = T.StructType([
        T.StructField("run_id", T.StringType(), False),
        T.StructField("users", T.IntegerType(), False),
        T.StructField("avg_trip_end_to_prediction_ms", T.DoubleType(), False),
        T.StructField("max_trip_end_to_prediction_ms", T.DoubleType(), False),
        T.StructField("avg_prediction_to_segments_ms", T.DoubleType(), False),
        T.StructField("max_prediction_to_segments_ms", T.DoubleType(), False),
        T.StructField("avg_trip_end_to_segments_ms", T.DoubleType(), False),
        T.StructField("max_trip_end_to_segments_ms", T.DoubleType(), False),
        T.StructField("reported_at", T.TimestampType(), False),
    ])
    spark.createDataFrame(summary, schema=schema).write.format("delta").mode("append").saveAsTable(benchmark_name)

    print("END_TO_SEGMENT_REPORT", {
        **{k: v for k, v in summary[0].items() if k != "reported_at"},
        "per_trip": {
            r["trip_id"]: {
                "expected_last_sequence": int(r["expected_last_sequence"]),
                "max_predicted_sequence": int(r["max_predicted_sequence"]),
                "segment_point_coverage": int(r["segment_point_coverage"]),
                "segment_count": int(r["segment_count"]),
                "trip_end_to_prediction_ms": float(r["trip_end_to_prediction_ms"]),
                "prediction_to_segments_ms": float(r["prediction_to_segments_ms"]),
                "trip_end_to_segments_ms": float(r["trip_end_to_segments_ms"]),
            }
            for r in rows
        },
        "benchmark_table": benchmark_name,
    })


if __name__ == "__main__":
    main()

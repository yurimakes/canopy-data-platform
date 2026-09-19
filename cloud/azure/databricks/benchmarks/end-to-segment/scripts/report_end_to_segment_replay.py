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
    p.add_argument("--segments-table", required=True)
    p.add_argument("--benchmark-table", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--users", type=int, required=True)
    p.add_argument("--timeout-seconds", type=int, default=180)
    p.add_argument("--poll-seconds", type=float, default=1.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    predictions_name = f"{args.catalog}.{args.schema}.{args.prediction_table}"
    segments_name = f"{args.catalog}.{args.schema}.{args.segments_table}"
    benchmark_name = f"{args.catalog}.{args.schema}.{args.benchmark_table}"
    prefix = f"replay:{args.run_id}:trip:"

    deadline = time.monotonic() + args.timeout_seconds
    segmented_trips = 0
    while time.monotonic() < deadline:
        segmented_trips = (
            spark.table(segments_name)
            .where(F.col("trip_id").startswith(prefix))
            .select("trip_id").distinct().count()
        )
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
    predictions = (
        spark.table(predictions_name)
        .where(F.col("trip_id").startswith(prefix))
        .groupBy("trip_id")
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
            F.max("segmented_at").alias("segments_ready_at"),
            F.sum("point_count").alias("segment_point_coverage"),
            F.count("*").alias("segment_count"),
        )
    )

    per_trip = (
        trip_ends.join(predictions, "trip_id", "inner")
        .join(segments, "trip_id", "inner")
        .withColumn(
            "trip_end_to_prediction_ms",
            (F.col("last_predicted_at").cast("double") - F.col("parsed_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "prediction_to_segments_ms",
            (F.col("segments_ready_at").cast("double") - F.col("last_predicted_at").cast("double")) * 1000.0,
        )
        .withColumn(
            "trip_end_to_segments_ms",
            (F.col("segments_ready_at").cast("double") - F.col("parsed_at").cast("double")) * 1000.0,
        )
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

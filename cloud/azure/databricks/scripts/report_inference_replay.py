"""Report and persist latency metrics for an inference replay run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F, types as T


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--input-table", required=True)
    parser.add_argument("--output-table", required=True)
    parser.add_argument("--benchmark-table", required=True)
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    input_name = f"{args.catalog}.{args.schema}.{args.input_table}"
    output_name = f"{args.catalog}.{args.schema}.{args.output_table}"
    benchmark_name = f"{args.catalog}.{args.schema}.{args.benchmark_table}"

    source = spark.table(input_name).where(F.col("trip_id") == args.trip_id)
    predictions = spark.table(output_name).where(F.col("trip_id") == args.trip_id)

    source_rows = source.count()
    prediction_rows = predictions.count()

    if prediction_rows == 0:
        raise ValueError(f"no predictions found for trip_id {args.trip_id!r} in {output_name}")

    agg = predictions.agg(
        F.min("sequence").alias("min_sequence"),
        F.max("sequence").alias("max_sequence"),
        F.min("features_processed_at").alias("first_features_processed_at"),
        F.max("features_processed_at").alias("last_features_processed_at"),
        F.min("predicted_at").alias("first_predicted_at"),
        F.max("predicted_at").alias("last_predicted_at"),
        F.avg(
            (F.col("predicted_at").cast("double") - F.col("features_processed_at").cast("double")) * 1000.0
        ).alias("avg_features_to_prediction_ms"),
        F.expr(
            "percentile_approx((cast(predicted_at as double) - cast(features_processed_at as double)) * 1000.0, 0.5)"
        ).alias("p50_features_to_prediction_ms"),
        F.expr(
            "percentile_approx((cast(predicted_at as double) - cast(features_processed_at as double)) * 1000.0, 0.95)"
        ).alias("p95_features_to_prediction_ms"),
    ).collect()[0]

    first_features = agg["first_features_processed_at"]
    last_prediction = agg["last_predicted_at"]
    inference_wall_ms = None
    if first_features is not None and last_prediction is not None:
        inference_wall_ms = (last_prediction - first_features).total_seconds() * 1000.0

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    row = [{
        "run_id": args.run_id,
        "trip_id": args.trip_id,
        "source_rows": source_rows,
        "prediction_rows": prediction_rows,
        "min_sequence": agg["min_sequence"],
        "max_sequence": agg["max_sequence"],
        "first_features_processed_at": first_features,
        "last_features_processed_at": agg["last_features_processed_at"],
        "first_predicted_at": agg["first_predicted_at"],
        "last_predicted_at": last_prediction,
        "inference_wall_ms": inference_wall_ms,
        "avg_features_to_prediction_ms": agg["avg_features_to_prediction_ms"],
        "p50_features_to_prediction_ms": agg["p50_features_to_prediction_ms"],
        "p95_features_to_prediction_ms": agg["p95_features_to_prediction_ms"],
        "reported_at": now,
    }]

    schema = T.StructType([
        T.StructField("run_id", T.StringType(), False),
        T.StructField("trip_id", T.StringType(), False),
        T.StructField("source_rows", T.LongType(), False),
        T.StructField("prediction_rows", T.LongType(), False),
        T.StructField("min_sequence", T.LongType(), True),
        T.StructField("max_sequence", T.LongType(), True),
        T.StructField("first_features_processed_at", T.TimestampType(), True),
        T.StructField("last_features_processed_at", T.TimestampType(), True),
        T.StructField("first_predicted_at", T.TimestampType(), True),
        T.StructField("last_predicted_at", T.TimestampType(), True),
        T.StructField("inference_wall_ms", T.DoubleType(), True),
        T.StructField("avg_features_to_prediction_ms", T.DoubleType(), True),
        T.StructField("p50_features_to_prediction_ms", T.DoubleType(), True),
        T.StructField("p95_features_to_prediction_ms", T.DoubleType(), True),
        T.StructField("reported_at", T.TimestampType(), False),
    ])

    report_df = spark.createDataFrame(row, schema=schema)
    report_df.write.format("delta").mode("append").saveAsTable(benchmark_name)

    print(
        "REPLAY_REPORT",
        {
            "run_id": args.run_id,
            "trip_id": args.trip_id,
            "source_rows": source_rows,
            "prediction_rows": prediction_rows,
            "sequence": f"{agg['min_sequence']}..{agg['max_sequence']}",
            "inference_wall_ms": inference_wall_ms,
            "avg_features_to_prediction_ms": agg["avg_features_to_prediction_ms"],
            "p50_features_to_prediction_ms": agg["p50_features_to_prediction_ms"],
            "p95_features_to_prediction_ms": agg["p95_features_to_prediction_ms"],
            "benchmark_table": benchmark_name,
        },
    )


if __name__ == "__main__":
    main()

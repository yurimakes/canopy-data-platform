"""Wait for replay inference completion and report inference-stage latency only."""

from __future__ import annotations

import argparse
import time

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--prediction-table", required=True)
    p.add_argument("--arrival-table", required=True)
    p.add_argument("--pipeline-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--users", type=int, required=True)
    p.add_argument("--timeout-seconds", type=int, default=180)
    p.add_argument("--poll-seconds", type=float, default=1.0)
    return p.parse_args()



def stream_progress_report(
    spark: SparkSession,
    pipeline_id: str,
    window_start,
    window_end,
) -> dict:
    """Return best-effort Lakeflow stream-progress metrics for the benchmark window."""
    try:
        progress = spark.sql(
            f"""
            SELECT
              timestamp,
              get_json_object(details, '$.stream_progress.progress_json') AS progress_json
            FROM event_log('{pipeline_id}')
            WHERE event_type = 'stream_progress'
              AND timestamp >= TIMESTAMP '{window_start}'
              AND timestamp <= TIMESTAMP '{window_end}'
            ORDER BY timestamp
            """
        ).where(F.col("progress_json").isNotNull())

        parsed = (
            progress.select(
                "timestamp",
                F.get_json_object("progress_json", "$.batchId").cast("long").alias("batch_id"),
                F.get_json_object(
                    "progress_json",
                    "$.durationMs.triggerExecution",
                ).cast("double").alias("trigger_execution_ms"),
                F.get_json_object(
                    "progress_json",
                    "$.durationMs.addBatch",
                ).cast("double").alias("add_batch_ms"),
                F.get_json_object(
                    "progress_json",
                    "$.durationMs.queryPlanning",
                ).cast("double").alias("query_planning_ms"),
                F.get_json_object(
                    "progress_json",
                    "$.durationMs.commitBatch",
                ).cast("double").alias("commit_batch_ms"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].numRowsUpdated",
                ).cast("long").alias("num_rows_updated"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].numRowsTotal",
                ).cast("long").alias("num_rows_total"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].numShufflePartitions",
                ).cast("long").alias("num_shuffle_partitions"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].numStateStoreInstances",
                ).cast("long").alias("num_state_store_instances"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].allUpdatesTimeMs",
                ).cast("double").alias("all_updates_time_ms"),
                F.get_json_object(
                    "progress_json",
                    "$.stateOperators[0].commitTimeMs",
                ).cast("double").alias("state_commit_time_ms"),
            )
        )

        rows = parsed.collect()
        if not rows:
            return {
                "available": False,
                "reason": "no stream_progress rows in benchmark window",
            }

        def numeric_values(name: str) -> list[float]:
            return [float(row[name]) for row in rows if row[name] is not None]

        def summarize(name: str) -> dict | None:
            values = numeric_values(name)
            if not values:
                return None
            return {
                "avg": sum(values) / len(values),
                "max": max(values),
            }

        partition_values = sorted(
            {
                int(row["num_shuffle_partitions"])
                for row in rows
                if row["num_shuffle_partitions"] is not None
            }
        )
        state_store_values = sorted(
            {
                int(row["num_state_store_instances"])
                for row in rows
                if row["num_state_store_instances"] is not None
            }
        )

        return {
            "available": True,
            "stream_progress_rows": len(rows),
            "num_shuffle_partitions": partition_values,
            "num_state_store_instances": state_store_values,
            "trigger_execution_ms": summarize("trigger_execution_ms"),
            "add_batch_ms": summarize("add_batch_ms"),
            "query_planning_ms": summarize("query_planning_ms"),
            "commit_batch_ms": summarize("commit_batch_ms"),
            "all_updates_time_ms": summarize("all_updates_time_ms"),
            "state_commit_time_ms": summarize("state_commit_time_ms"),
            "num_rows_updated": summarize("num_rows_updated"),
            "num_rows_total": summarize("num_rows_total"),
            "batch_ids": [
                int(row["batch_id"])
                for row in rows
                if row["batch_id"] is not None
            ],
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    predictions_name = f"{args.catalog}.{args.schema}.{args.prediction_table}"
    arrivals_name = f"{args.catalog}.{args.schema}.{args.arrival_table}"
    prefix = f"replay:{args.run_id}:trip:"

    trip_ends = (
        spark.table(trip_end_name)
        .where(F.col("trip_id").startswith(prefix))
        .select("trip_id", "parsed_at", "expected_last_sequence")
    )

    deadline = time.monotonic() + args.timeout_seconds
    completed_trips = 0
    while time.monotonic() < deadline:
        max_predictions = (
            spark.table(predictions_name)
            .where(F.col("trip_id").startswith(prefix))
            .groupBy("trip_id")
            .agg(F.max("sequence").alias("max_predicted_sequence"))
        )
        completed_trips = (
            trip_ends.alias("t")
            .join(max_predictions.alias("p"), "trip_id", "left")
            .where(
                F.col("p.max_predicted_sequence")
                >= F.col("t.expected_last_sequence")
            )
            .select("trip_id")
            .distinct()
            .count()
        )
        if completed_trips >= args.users:
            break
        print(
            "INFERENCE_WAIT",
            {"completed_trips": completed_trips, "expected": args.users},
        )
        time.sleep(args.poll_seconds)

    if completed_trips < args.users:
        raise TimeoutError(
            f"timed out with {completed_trips}/{args.users} inference-complete trips "
            f"for {args.run_id}"
        )

    prediction_rows = (
        spark.table(predictions_name)
        .where(F.col("trip_id").startswith(prefix))
        .select(
            "event_id",
            "trip_id",
            "sequence",
            "processor_entered_at",
            "feature_compute_started_at",
            "features_processed_at",
            "predicted_at",
        )
    )

    arrivals = (
        spark.table(arrivals_name)
        .where(F.col("run_id") == args.run_id)
        .select(
            "event_id",
            "trip_id",
            "sequence",
            "replay_visible_at",
        )
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
            F.col("p.processor_entered_at").alias("processor_entered_at"),
            F.col("p.feature_compute_started_at").alias("feature_compute_started_at"),
            F.col("p.features_processed_at").alias("features_processed_at"),
            F.col("p.predicted_at").alias("predicted_at"),
        )
        .withColumn(
            "visible_to_processor_ms",
            (
                F.col("processor_entered_at").cast("double")
                - F.col("replay_visible_at").cast("double")
            )
            * 1000.0,
        )
        .withColumn(
            "processor_to_feature_start_ms",
            (
                F.col("feature_compute_started_at").cast("double")
                - F.col("processor_entered_at").cast("double")
            )
            * 1000.0,
        )
        .withColumn(
            "feature_compute_ms",
            (
                F.col("features_processed_at").cast("double")
                - F.col("feature_compute_started_at").cast("double")
            )
            * 1000.0,
        )
        .withColumn(
            "visible_to_features_ms",
            (
                F.col("features_processed_at").cast("double")
                - F.col("replay_visible_at").cast("double")
            )
            * 1000.0,
        )
        .withColumn(
            "features_to_prediction_ms",
            (
                F.col("predicted_at").cast("double")
                - F.col("features_processed_at").cast("double")
            )
            * 1000.0,
        )
        .withColumn(
            "visible_to_prediction_ms",
            (
                F.col("predicted_at").cast("double")
                - F.col("replay_visible_at").cast("double")
            )
            * 1000.0,
        )
    )

    stage_summary = stage_rows.agg(
        F.count("*").alias("rows"),
        F.avg("visible_to_processor_ms").alias("avg_visible_to_processor_ms"),
        F.expr("percentile_approx(visible_to_processor_ms, 0.50)").alias(
            "p50_visible_to_processor_ms"
        ),
        F.expr("percentile_approx(visible_to_processor_ms, 0.95)").alias(
            "p95_visible_to_processor_ms"
        ),
        F.max("visible_to_processor_ms").alias("max_visible_to_processor_ms"),
        F.avg("processor_to_feature_start_ms").alias(
            "avg_processor_to_feature_start_ms"
        ),
        F.expr(
            "percentile_approx(processor_to_feature_start_ms, 0.50)"
        ).alias("p50_processor_to_feature_start_ms"),
        F.expr(
            "percentile_approx(processor_to_feature_start_ms, 0.95)"
        ).alias("p95_processor_to_feature_start_ms"),
        F.max("processor_to_feature_start_ms").alias(
            "max_processor_to_feature_start_ms"
        ),
        F.avg("feature_compute_ms").alias("avg_feature_compute_ms"),
        F.expr("percentile_approx(feature_compute_ms, 0.50)").alias(
            "p50_feature_compute_ms"
        ),
        F.expr("percentile_approx(feature_compute_ms, 0.95)").alias(
            "p95_feature_compute_ms"
        ),
        F.max("feature_compute_ms").alias("max_feature_compute_ms"),
        F.avg("visible_to_features_ms").alias("avg_visible_to_features_ms"),
        F.expr("percentile_approx(visible_to_features_ms, 0.50)").alias(
            "p50_visible_to_features_ms"
        ),
        F.expr("percentile_approx(visible_to_features_ms, 0.95)").alias(
            "p95_visible_to_features_ms"
        ),
        F.max("visible_to_features_ms").alias("max_visible_to_features_ms"),
        F.avg("features_to_prediction_ms").alias(
            "avg_features_to_prediction_ms"
        ),
        F.expr(
            "percentile_approx(features_to_prediction_ms, 0.50)"
        ).alias("p50_features_to_prediction_ms"),
        F.expr(
            "percentile_approx(features_to_prediction_ms, 0.95)"
        ).alias("p95_features_to_prediction_ms"),
        F.max("features_to_prediction_ms").alias(
            "max_features_to_prediction_ms"
        ),
        F.avg("visible_to_prediction_ms").alias(
            "avg_visible_to_prediction_ms"
        ),
        F.expr(
            "percentile_approx(visible_to_prediction_ms, 0.50)"
        ).alias("p50_visible_to_prediction_ms"),
        F.expr(
            "percentile_approx(visible_to_prediction_ms, 0.95)"
        ).alias("p95_visible_to_prediction_ms"),
        F.max("visible_to_prediction_ms").alias(
            "max_visible_to_prediction_ms"
        ),
    ).collect()[0]

    final_sequence_stage = (
        stage_rows.alias("s")
        .join(
            trip_ends.select(
                "trip_id",
                "parsed_at",
                F.col("expected_last_sequence").alias("final_sequence"),
            ).alias("t"),
            (F.col("s.trip_id") == F.col("t.trip_id"))
            & (F.col("s.sequence") == F.col("t.final_sequence")),
            "inner",
        )
        .select(
            F.col("s.trip_id").alias("trip_id"),
            "replay_visible_at",
            "processor_entered_at",
            "feature_compute_started_at",
            "features_processed_at",
            "predicted_at",
            "visible_to_processor_ms",
            "processor_to_feature_start_ms",
            "feature_compute_ms",
            "visible_to_features_ms",
            "features_to_prediction_ms",
            "visible_to_prediction_ms",
            (
                (
                    F.col("s.predicted_at").cast("double")
                    - F.col("t.parsed_at").cast("double")
                )
                * 1000.0
            ).alias("trip_end_to_prediction_ms"),
            F.greatest(
                F.lit(0.0),
                (
                    F.col("s.predicted_at").cast("double")
                    - F.col("t.parsed_at").cast("double")
                )
                * 1000.0,
            ).alias("prediction_readiness_wait_ms"),
        )
        .collect()
    )

    benchmark_window = stage_rows.agg(
        F.min("replay_visible_at").alias("window_start"),
        F.max("predicted_at").alias("window_end"),
    ).collect()[0]
    stream_metrics = stream_progress_report(
        spark,
        args.pipeline_id,
        benchmark_window["window_start"],
        benchmark_window["window_end"],
    )

    readiness_values = [
        float(r["prediction_readiness_wait_ms"])
        for r in final_sequence_stage
    ]
    raw_trip_end_values = [
        float(r["trip_end_to_prediction_ms"])
        for r in final_sequence_stage
    ]
    final_sequence_summary = {
        "avg_prediction_readiness_wait_ms": (
            sum(readiness_values) / len(readiness_values)
        ),
        "max_prediction_readiness_wait_ms": max(readiness_values),
        "avg_signed_trip_end_to_prediction_ms": (
            sum(raw_trip_end_values) / len(raw_trip_end_values)
        ),
        "min_signed_trip_end_to_prediction_ms": min(raw_trip_end_values),
        "max_signed_trip_end_to_prediction_ms": max(raw_trip_end_values),
    }

    summary = {
        name: (
            int(stage_summary[name])
            if name == "rows"
            else float(stage_summary[name])
        )
        for name in stage_summary.__fields__
    }

    print(
        "INFERENCE_ONLY_REPORT",
        {
            "run_id": args.run_id,
            "completed_trips": completed_trips,
            "all_prediction_rows": summary,
            "stream_progress": stream_metrics,
            "final_sequence_summary": final_sequence_summary,
            "final_sequence_per_trip": {
                r["trip_id"]: {
                    "replay_visible_at": str(r["replay_visible_at"]),
                    "processor_entered_at": str(r["processor_entered_at"]),
                    "feature_compute_started_at": str(
                        r["feature_compute_started_at"]
                    ),
                    "features_processed_at": str(r["features_processed_at"]),
                    "predicted_at": str(r["predicted_at"]),
                    "visible_to_processor_ms": float(
                        r["visible_to_processor_ms"]
                    ),
                    "processor_to_feature_start_ms": float(
                        r["processor_to_feature_start_ms"]
                    ),
                    "feature_compute_ms": float(r["feature_compute_ms"]),
                    "visible_to_features_ms": float(
                        r["visible_to_features_ms"]
                    ),
                    "features_to_prediction_ms": float(
                        r["features_to_prediction_ms"]
                    ),
                    "visible_to_prediction_ms": float(
                        r["visible_to_prediction_ms"]
                    ),
                    "trip_end_to_prediction_ms": float(
                        r["trip_end_to_prediction_ms"]
                    ),
                    "prediction_readiness_wait_ms": float(
                        r["prediction_readiness_wait_ms"]
                    ),
                }
                for r in final_sequence_stage
            },
        },
    )


if __name__ == "__main__":
    main()

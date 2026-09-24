"""Observe one trip from Event Hubs through the final Gold complete payload."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--gps-table", required=True)
    parser.add_argument("--trip-ended-table", required=True)
    parser.add_argument("--complete-payloads-table", required=True)
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    return parser.parse_args()


def ms(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds() * 1000.0


def percentile_expr(column: str, percentile: float) -> F.Column:
    return F.expr(f"percentile_approx({column}, {percentile}, 10000)")


def main() -> None:
    args = parse_args()
    if not args.trip_id.strip():
        raise ValueError("trip_id is required")

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    gps_name = f"{args.catalog}.{args.schema}.{args.gps_table}"
    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    complete_payloads_name = f"{args.catalog}.{args.schema}.{args.complete_payloads_table}"

    deadline = time.monotonic() + args.timeout_seconds
    print("EH_TO_GOLD_OBSERVER_READY", json.dumps({"trip_id": args.trip_id}))

    while time.monotonic() < deadline:
        trip_end_rows = (
            spark.table(trip_end_name)
            .where(F.col("trip_id") == args.trip_id)
            .orderBy(F.col("parsed_at").desc())
            .limit(1)
            .collect()
        )
        if not trip_end_rows:
            time.sleep(args.poll_seconds)
            continue

        trip_end = trip_end_rows[0]
        expected_last = int(trip_end["expected_last_sequence"])

        gps_frame = spark.table(gps_name).where(F.col("trip_id") == args.trip_id)
        gps_state = (
            gps_frame.agg(
                F.count("*").alias("gps_rows"),
                F.min("sequence").alias("min_sequence"),
                F.max("sequence").alias("max_sequence"),
                F.min("event_time").alias("first_event_time"),
                F.max("event_time").alias("last_event_time"),
                F.max("event_hub_enqueued_at").alias("last_gps_event_hub_enqueued_at"),
                F.max("validated_at").alias("last_gps_validated_at"),
            )
            .collect()[0]
        )

        if (
            int(gps_state["gps_rows"] or 0) < expected_last
            or int(gps_state["max_sequence"] or 0) < expected_last
        ):
            time.sleep(args.poll_seconds)
            continue

        result_rows = (
            spark.table(complete_payloads_name)
            .where(F.col("trip_id") == args.trip_id)
            .orderBy(F.col("sealed_at").desc())
            .limit(1)
            .collect()
        )
        if not result_rows:
            time.sleep(args.poll_seconds)
            continue

        result = result_rows[0]

        gps_latency = gps_frame.select(
            (
                (F.col("validated_at").cast("double")
                 - F.col("event_hub_enqueued_at").cast("double"))
                * F.lit(1000.0)
            ).alias("eh_to_validated_ms")
        )
        gps_metrics = (
            gps_latency.agg(
                percentile_expr("eh_to_validated_ms", 0.5).alias("p50"),
                percentile_expr("eh_to_validated_ms", 0.95).alias("p95"),
                F.max("eh_to_validated_ms").alias("max"),
            )
            .collect()[0]
        )

        trip_end_enqueued = trip_end["event_hub_enqueued_at"]
        trip_end_parsed = trip_end["parsed_at"]
        sealed_at = result["sealed_at"]
        visible_at = datetime.now(timezone.utc).replace(tzinfo=None)

        segments = result["segments"] or []
        prediction_count = sum(int(segment["prediction_count"]) for segment in segments)
        final_segment_end = segments[-1]["end_time"] if segments else None

        report = {
            "trip_id": args.trip_id,
            "status": "PASS",
            "gps_rows": int(gps_state["gps_rows"]),
            "min_sequence": int(gps_state["min_sequence"]),
            "max_sequence": int(gps_state["max_sequence"]),
            "expected_last_sequence": expected_last,
            "segment_count": len(segments),
            "prediction_count": prediction_count,
            "timestamps": {
                "first_event_time": str(gps_state["first_event_time"]),
                "last_event_time": str(gps_state["last_event_time"]),
                "last_gps_event_hub_enqueued_at": str(gps_state["last_gps_event_hub_enqueued_at"]),
                "last_gps_validated_at": str(gps_state["last_gps_validated_at"]),
                "trip_end_event_hub_enqueued_at": str(trip_end_enqueued),
                "trip_end_parsed_at": str(trip_end_parsed),
                "gold_final_at": str(sealed_at),
                "observer_visible_at": str(visible_at),
                "final_segment_end": str(final_segment_end),
            },
            "latency_ms": {
                "gps_eventhub_to_validated_p50": float(gps_metrics["p50"]),
                "gps_eventhub_to_validated_p95": float(gps_metrics["p95"]),
                "gps_eventhub_to_validated_max": float(gps_metrics["max"]),
                "trip_end_eventhub_to_parsed": ms(trip_end_parsed, trip_end_enqueued),
                "trip_end_parsed_to_gold_final": ms(sealed_at, trip_end_parsed),
                "trip_end_eventhub_to_gold_final": ms(sealed_at, trip_end_enqueued),
                "last_gps_eventhub_to_gold_final": ms(
                    sealed_at, gps_state["last_gps_event_hub_enqueued_at"]
                ),
                "last_gps_validated_to_gold_final": ms(
                    sealed_at, gps_state["last_gps_validated_at"]
                ),
            },
            "observer_delay_ms": {
                "gold_final_to_observer_visible": ms(visible_at, sealed_at),
                "trip_end_eventhub_to_observer_visible": ms(visible_at, trip_end_enqueued),
            },
            "model": {
                "name": result["model_name"],
                "version": result["model_version"],
                "feature_version": result["feature_version"],
            },
        }
        print("EH_TO_GOLD_LATENCY_REPORT", json.dumps(report, default=str))
        return

    raise TimeoutError(
        f"timed out waiting for final Gold payload trip_id={args.trip_id}"
    )


if __name__ == "__main__":
    main()

"""Observe one externally published trip through sandbox ingestion only."""

from __future__ import annotations

import argparse
import json
import time

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--bronze-table", required=True)
    p.add_argument("--gps-table", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--trip-id", required=True)
    p.add_argument("--timeout-seconds", type=int, default=600)
    p.add_argument("--poll-seconds", type=float, default=0.5)
    return p.parse_args()


def latency_ms(later: str, earlier: str) -> F.Column:
    return (
        F.col(later).cast("double") - F.col(earlier).cast("double")
    ) * F.lit(1000.0)


def percentile_expr(column: str, percentile: float) -> F.Column:
    return F.expr(f"percentile_approx({column}, {percentile}, 10000)")


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    bronze_name = f"{args.catalog}.{args.schema}.{args.bronze_table}"
    gps_name = f"{args.catalog}.{args.schema}.{args.gps_table}"
    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"

    deadline = time.monotonic() + args.timeout_seconds
    print("INGESTION_OBSERVER_READY", {"trip_id": args.trip_id})

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
                F.count("*").alias("row_count"),
                F.max("sequence").alias("max_sequence"),
            ).collect()[0]
        )

        if int(gps_state["row_count"] or 0) < expected_last:
            time.sleep(args.poll_seconds)
            continue
        if int(gps_state["max_sequence"] or 0) < expected_last:
            time.sleep(args.poll_seconds)
            continue

        bronze_trip = (
            spark.table(bronze_name)
            .where(F.col("raw_payload").contains(args.trip_id))
        )
        bronze_count = bronze_trip.count()
        if bronze_count < expected_last + 1:
            time.sleep(args.poll_seconds)
            continue

        gps_latency = (
            gps_frame
            .select(
                "*",
                latency_ms("bronze_ingested_at", "event_hub_enqueued_at").alias("eh_to_bronze_ms"),
                latency_ms("parsed_at", "bronze_ingested_at").alias("bronze_to_parsed_ms"),
                latency_ms("validated_at", "parsed_at").alias("parsed_to_validated_ms"),
                latency_ms("validated_at", "bronze_ingested_at").alias("bronze_to_validated_ms"),
                latency_ms("validated_at", "event_hub_enqueued_at").alias("eh_to_validated_ms"),
            )
        )

        metrics = [
            "eh_to_bronze_ms",
            "bronze_to_parsed_ms",
            "parsed_to_validated_ms",
            "bronze_to_validated_ms",
            "eh_to_validated_ms",
        ]

        agg_columns = [F.count("*").alias("rows")]
        for metric in metrics:
            agg_columns.extend(
                [
                    percentile_expr(metric, 0.5).alias(f"{metric}_p50"),
                    percentile_expr(metric, 0.95).alias(f"{metric}_p95"),
                    F.max(metric).alias(f"{metric}_max"),
                ]
            )

        gps_report = gps_latency.agg(*agg_columns).collect()[0].asDict()

        trip_end_enqueued = trip_end["event_hub_enqueued_at"]
        trip_end_bronze = trip_end["bronze_ingested_at"]
        trip_end_parsed = trip_end["parsed_at"]

        def ms(later, earlier):
            return (later - earlier).total_seconds() * 1000.0

        report = {
            "trip_id": args.trip_id,
            "status": "PASS",
            "expected_last_sequence": expected_last,
            "gps_rows": int(gps_report.pop("rows")),
            "bronze_rows_matching_trip": int(bronze_count),
            "gps_latency_ms": gps_report,
            "trip_end_latency_ms": {
                "eh_to_bronze": ms(trip_end_bronze, trip_end_enqueued),
                "bronze_to_parsed": ms(trip_end_parsed, trip_end_bronze),
                "eh_to_parsed": ms(trip_end_parsed, trip_end_enqueued),
            },
            "trip_end_timestamps": {
                "event_hub_enqueued_at": str(trip_end_enqueued),
                "bronze_ingested_at": str(trip_end_bronze),
                "parsed_at": str(trip_end_parsed),
            },
        }
        print("INGESTION_LATENCY_REPORT", json.dumps(report, default=str))
        return

    raise TimeoutError(f"timed out waiting for ingestion trip_id={args.trip_id}")


if __name__ == "__main__":
    main()

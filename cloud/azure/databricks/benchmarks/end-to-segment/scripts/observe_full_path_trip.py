"""Observe one externally published trip across ingestion and integrated segmentation."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--gps-table", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--segments-table", required=True)
    p.add_argument("--trip-id", required=True)
    p.add_argument("--timeout-seconds", type=int, default=600)
    p.add_argument("--poll-seconds", type=float, default=0.5)
    return p.parse_args()


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ms(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds() * 1000.0


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    gps_name = f"{args.catalog}.{args.schema}.{args.gps_table}"
    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    segments_name = f"{args.catalog}.{args.schema}.{args.segments_table}"

    deadline = time.monotonic() + args.timeout_seconds
    print("FULL_PATH_OBSERVER_READY", {"trip_id": args.trip_id})

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

        gps = (
            spark.table(gps_name)
            .where(F.col("trip_id") == args.trip_id)
            .agg(
                F.count("*").alias("row_count"),
                F.max("sequence").alias("max_sequence"),
                F.max("event_hub_enqueued_at").alias("final_gps_event_hub_enqueued_at"),
                F.max("bronze_ingested_at").alias("final_gps_bronze_ingested_at"),
                F.max("parsed_at").alias("final_gps_parsed_at"),
                F.max("validated_at").alias("final_gps_validated_at"),
            )
            .collect()[0]
        )
        if int(gps["row_count"] or 0) < expected_last or int(gps["max_sequence"] or 0) < expected_last:
            time.sleep(args.poll_seconds)
            continue

        segment_rows = (
            spark.table(segments_name)
            .where(F.col("trip_id") == args.trip_id)
            .orderBy("segment_index")
            .collect()
        )
        if not segment_rows:
            time.sleep(args.poll_seconds)
            continue
        if int(segment_rows[-1]["end_sequence"]) != expected_last:
            time.sleep(args.poll_seconds)
            continue

        visible_at = now_utc_naive()
        segmented_at = max(r["segmented_at"] for r in segment_rows)

        trip_end_enqueued = trip_end["event_hub_enqueued_at"]
        trip_end_bronze = trip_end["bronze_ingested_at"]
        trip_end_parsed = trip_end["parsed_at"]
        final_gps_enqueued = gps["final_gps_event_hub_enqueued_at"]
        final_gps_bronze = gps["final_gps_bronze_ingested_at"]
        final_gps_parsed = gps["final_gps_parsed_at"]
        final_gps_validated = gps["final_gps_validated_at"]

        report = {
            "trip_id": args.trip_id,
            "status": "PASS",
            "expected_last_sequence": expected_last,
            "gps_row_count": int(gps["row_count"]),
            "segment_count": len(segment_rows),
            "modes": [r["mode"] for r in segment_rows],
            "ranges": [[int(r["start_sequence"]), int(r["end_sequence"])] for r in segment_rows],
            "timestamps": {
                "final_gps_event_hub_enqueued_at": str(final_gps_enqueued),
                "final_gps_bronze_ingested_at": str(final_gps_bronze),
                "final_gps_parsed_at": str(final_gps_parsed),
                "final_gps_validated_at": str(final_gps_validated),
                "trip_end_event_hub_enqueued_at": str(trip_end_enqueued),
                "trip_end_bronze_ingested_at": str(trip_end_bronze),
                "trip_end_parsed_at": str(trip_end_parsed),
                "segmented_at": str(segmented_at),
                "segments_visible_at": str(visible_at),
            },
            "latency_ms": {
                "final_gps_eventhub_to_bronze": ms(final_gps_bronze, final_gps_enqueued),
                "final_gps_bronze_to_validated": ms(final_gps_validated, final_gps_bronze),
                "final_gps_eventhub_to_validated": ms(final_gps_validated, final_gps_enqueued),
                "trip_end_eventhub_to_bronze": ms(trip_end_bronze, trip_end_enqueued),
                "trip_end_bronze_to_parsed": ms(trip_end_parsed, trip_end_bronze),
                "trip_end_eventhub_to_parsed": ms(trip_end_parsed, trip_end_enqueued),
                "trip_end_parsed_to_segmented": ms(segmented_at, trip_end_parsed),
                "trip_end_eventhub_to_segmented": ms(segmented_at, trip_end_enqueued),
                "segmented_to_visible": ms(visible_at, segmented_at),
                "trip_end_eventhub_to_visible": ms(visible_at, trip_end_enqueued),
            },
        }
        print("FULL_PATH_BENCHMARK_REPORT", json.dumps(report, default=str))
        return

    raise TimeoutError(f"timed out waiting for full path trip_id={args.trip_id}")


if __name__ == "__main__":
    main()

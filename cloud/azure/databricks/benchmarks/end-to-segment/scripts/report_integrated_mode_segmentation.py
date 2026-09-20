"""Report correctness and visibility latency for the integrated segmentation prototype."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--arrival-table", required=True)
    p.add_argument("--segments-table", required=True)
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
    arrival_name = f"{args.catalog}.{args.schema}.{args.arrival_table}"
    segments_name = f"{args.catalog}.{args.schema}.{args.segments_table}"
    prefix = f"replay:{args.run_id}:trip:"

    deadline = time.monotonic() + args.timeout_seconds
    first_visible_at: dict[str, datetime] = {}

    while time.monotonic() < deadline:
        trip_ids = [
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
        for trip_id in trip_ids:
            first_visible_at.setdefault(trip_id, observed_at)

        if len(first_visible_at) >= args.users:
            break

        print(
            "INTEGRATED_SEGMENT_WAIT",
            {"visible_trips": len(first_visible_at), "expected": args.users},
        )
        time.sleep(args.poll_seconds)

    if len(first_visible_at) < args.users:
        raise TimeoutError(
            f"timed out with {len(first_visible_at)}/{args.users} segmented trips "
            f"for run_id={args.run_id}"
        )

    trip_ends = {
        row["trip_id"]: row
        for row in (
            spark.table(trip_end_name)
            .where(F.col("trip_id").startswith(prefix))
            .select(
                "trip_id",
                "user_id",
                "expected_last_sequence",
                "processing_generation",
                F.col("parsed_at").alias("trip_end_parsed_at"),
            )
            .collect()
        )
    }

    arrivals = {
        row["trip_id"]: row["final_gps_visible_at"]
        for row in (
            spark.table(arrival_name)
            .where(F.col("run_id") == args.run_id)
            .groupBy("trip_id")
            .agg(F.max("replay_visible_at").alias("final_gps_visible_at"))
            .collect()
        )
    }

    segment_rows = (
        spark.table(segments_name)
        .where(F.col("trip_id").startswith(prefix))
        .orderBy("trip_id", "segment_index")
        .collect()
    )

    by_trip: dict[str, list] = {}
    for row in segment_rows:
        by_trip.setdefault(row["trip_id"], []).append(row)

    reports = {}
    for trip_id, visible_at in first_visible_at.items():
        if trip_id not in trip_ends:
            raise AssertionError(f"missing trip_end for {trip_id}")
        rows = by_trip.get(trip_id, [])
        if not rows:
            raise AssertionError(f"missing segments for {trip_id}")

        trip_end = trip_ends[trip_id]
        expected_last = int(trip_end["expected_last_sequence"])
        indices = [int(r["segment_index"]) for r in rows]
        starts = [int(r["start_sequence"]) for r in rows]
        ends = [int(r["end_sequence"]) for r in rows]
        point_count = sum(int(r["point_count"]) for r in rows)

        expected_indices = list(range(1, len(rows) + 1))
        contiguous_boundaries = starts[0] == 1 and all(
            starts[i] == ends[i - 1] + 1 for i in range(1, len(rows))
        )
        final_sequence_matches = ends[-1] == expected_last
        coverage_matches = point_count == expected_last
        indices_contiguous = indices == expected_indices
        generation_matches = all(
            int(r["processing_generation"]) == int(trip_end["processing_generation"])
            for r in rows
        )

        if not all(
            (
                contiguous_boundaries,
                final_sequence_matches,
                coverage_matches,
                indices_contiguous,
                generation_matches,
            )
        ):
            raise AssertionError(
                {
                    "trip_id": trip_id,
                    "contiguous_boundaries": contiguous_boundaries,
                    "final_sequence_matches": final_sequence_matches,
                    "coverage_matches": coverage_matches,
                    "indices_contiguous": indices_contiguous,
                    "generation_matches": generation_matches,
                    "starts": starts,
                    "ends": ends,
                    "point_count": point_count,
                    "expected_last_sequence": expected_last,
                }
            )

        parsed_at = trip_end["trip_end_parsed_at"]
        segmented_at = max(r["segmented_at"] for r in rows)
        final_gps_visible_at = arrivals.get(trip_id)
        if final_gps_visible_at is None:
            raise AssertionError(f"missing replay arrival marker for {trip_id}")

        reports[trip_id] = {
            "segment_count": len(rows),
            "modes": [r["mode"] for r in rows],
            "ranges": [
                [int(r["start_sequence"]), int(r["end_sequence"])] for r in rows
            ],
            "point_count": point_count,
            "expected_last_sequence": expected_last,
            "final_gps_visible_at": str(final_gps_visible_at),
            "trip_end_parsed_at": str(parsed_at),
            "segmented_at": str(segmented_at),
            "segments_visible_at": str(visible_at),
            "final_gps_to_segmented_at_ms": (
                segmented_at - final_gps_visible_at
            ).total_seconds()
            * 1000.0,
            "trip_end_to_segmented_at_ms": (
                segmented_at - parsed_at
            ).total_seconds()
            * 1000.0,
            "trip_end_to_visible_ms": (
                visible_at - parsed_at
            ).total_seconds()
            * 1000.0,
        }

    metric_names = (
        "final_gps_to_segmented_at_ms",
        "trip_end_to_segmented_at_ms",
        "trip_end_to_visible_ms",
    )
    summary = {}
    for metric in metric_names:
        values = sorted(float(report[metric]) for report in reports.values())
        count = len(values)
        def percentile(p: float) -> float:
            if count == 1:
                return values[0]
            index = round((count - 1) * p)
            return values[index]
        summary[metric] = {
            "count": count,
            "min": values[0],
            "avg": sum(values) / count,
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "max": values[-1],
        }

    print(
        "INTEGRATED_CORRECTNESS_REPORT",
        {
            "run_id": args.run_id,
            "users": args.users,
            "status": "PASS",
            "summary": summary,
            "trips": reports,
        },
    )


if __name__ == "__main__":
    main()

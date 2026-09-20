"""Continuously observe integrated segment visibility while replay production runs."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F, types as T


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--segments-table", required=True)
    p.add_argument("--observation-table", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--users", type=int, required=True)
    p.add_argument("--timeout-seconds", type=int, default=300)
    p.add_argument("--poll-seconds", type=float, default=0.5)
    return p.parse_args()


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    segments_name = f"{args.catalog}.{args.schema}.{args.segments_table}"
    observation_name = f"{args.catalog}.{args.schema}.{args.observation_table}"
    prefix = f"replay:{args.run_id}:trip:"

    schema = T.StructType([
        T.StructField("run_id", T.StringType(), False),
        T.StructField("trip_id", T.StringType(), False),
        T.StructField("segments_visible_at", T.TimestampType(), False),
    ])
    if not spark.catalog.tableExists(observation_name):
        spark.createDataFrame([], schema).write.format("delta").saveAsTable(observation_name)

    deadline = time.monotonic() + args.timeout_seconds
    seen: dict[str, datetime] = {}

    while time.monotonic() < deadline:
        rows = (
            spark.table(segments_name)
            .where(F.col("trip_id").startswith(prefix))
            .select("trip_id")
            .distinct()
            .collect()
        )
        observed_at = now_utc_naive()
        new_rows = []
        for row in rows:
            trip_id = row["trip_id"]
            if trip_id not in seen:
                seen[trip_id] = observed_at
                new_rows.append(
                    {
                        "run_id": args.run_id,
                        "trip_id": trip_id,
                        "segments_visible_at": observed_at,
                    }
                )
        if new_rows:
            (
                spark.createDataFrame(new_rows, schema=schema)
                .write.format("delta")
                .mode("append")
                .saveAsTable(observation_name)
            )
            print("INTEGRATED_SEGMENT_VISIBLE", json.dumps(new_rows, default=str))

        if len(seen) >= args.users:
            print(
                "INTEGRATED_OBSERVER_COMPLETE",
                {"run_id": args.run_id, "visible_trips": len(seen)},
            )
            return

        time.sleep(args.poll_seconds)

    raise TimeoutError(
        f"observer timed out with {len(seen)}/{args.users} trips for run_id={args.run_id}"
    )


if __name__ == "__main__":
    main()

"""Prepare a deterministic inference replay input table from an existing GPS trip."""

from __future__ import annotations

import argparse

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--source-table", required=True)
    parser.add_argument("--replay-table", required=True)
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    source = f"{args.catalog}.{args.schema}.{args.source_table}"
    target = f"{args.catalog}.{args.schema}.{args.replay_table}"

    replay = (
        spark.table(source)
        .where(F.col("trip_id") == args.trip_id)
        .orderBy("sequence")
    )

    row_count = replay.count()
    if row_count == 0:
        raise ValueError(f"trip_id {args.trip_id!r} produced zero rows from {source}")

    bounds = replay.agg(
        F.min("sequence").alias("min_sequence"),
        F.max("sequence").alias("max_sequence"),
        F.min("event_time").alias("min_event_time"),
        F.max("event_time").alias("max_event_time"),
    ).collect()[0]

    (
        replay.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target)
    )

    print(
        "REPLAY_PREPARED",
        {
            "run_id": args.run_id,
            "trip_id": args.trip_id,
            "source": source,
            "target": target,
            "rows": row_count,
            "min_sequence": bounds["min_sequence"],
            "max_sequence": bounds["max_sequence"],
            "min_event_time": str(bounds["min_event_time"]),
            "max_event_time": str(bounds["max_event_time"]),
        },
    )


if __name__ == "__main__":
    main()

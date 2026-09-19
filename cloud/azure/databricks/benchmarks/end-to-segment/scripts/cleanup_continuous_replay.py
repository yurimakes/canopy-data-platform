"""Delete disposable continuous-replay benchmark rows without touching production tables."""

from __future__ import annotations

import argparse

from pyspark.sql import SparkSession


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--replay-gps-table", required=True)
    p.add_argument("--replay-trip-ended-table", required=True)
    p.add_argument("--replay-arrival-table", required=True)
    p.add_argument("--benchmark-table", required=True)
    return p.parse_args()


def truncate_if_exists(spark: SparkSession, table_name: str) -> None:
    if not spark.catalog.tableExists(table_name):
        print("REPLAY_CLEANUP_SKIP_MISSING", table_name)
        return
    before = spark.table(table_name).count()
    spark.sql(f"TRUNCATE TABLE {table_name}")
    after = spark.table(table_name).count()
    print(
        "REPLAY_CLEANUP_TABLE",
        {"table": table_name, "rows_before": before, "rows_after": after},
    )


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    q = lambda name: f"{args.catalog}.{args.schema}.{name}"

    # Intentionally excludes replay_continuous_mode_predictions because that table
    # is owned by the Lakeflow inference pipeline. Its target/checkpoint is reset
    # by the subsequent full refresh.
    for name in (
        args.replay_gps_table,
        args.replay_trip_ended_table,
        args.replay_arrival_table,
        args.benchmark_table,
    ):
        truncate_if_exists(spark, q(name))

    print("REPLAY_CLEANUP_COMPLETE")


if __name__ == "__main__":
    main()

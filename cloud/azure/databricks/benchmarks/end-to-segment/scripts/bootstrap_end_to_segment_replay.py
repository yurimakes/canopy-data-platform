"""Create empty Delta source tables required by the continuous end-to-segment replay."""

from __future__ import annotations

import argparse

from pyspark.sql import SparkSession, types as T


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--gps-source-table", required=True)
    p.add_argument("--trip-end-source-table", required=True)
    p.add_argument("--segments-source-table", required=True)
    p.add_argument("--replay-gps-table", required=True)
    p.add_argument("--replay-trip-end-table", required=True)
    p.add_argument("--arrival-table", required=True)
    p.add_argument("--replay-segments-table", required=True)
    return p.parse_args()


def ensure_from_source(spark, source: str, target: str) -> None:
    if spark.catalog.tableExists(target):
        print("REPLAY_TABLE_EXISTS", target)
        return
    (
        spark.table(source).limit(0)
        .write.format("delta").mode("ignore").saveAsTable(target)
    )
    print("REPLAY_TABLE_CREATED", target)


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    q = lambda name: f"{args.catalog}.{args.schema}.{name}"

    ensure_from_source(spark, q(args.gps_source_table), q(args.replay_gps_table))
    ensure_from_source(spark, q(args.trip_end_source_table), q(args.replay_trip_end_table))
    ensure_from_source(spark, q(args.segments_source_table), q(args.replay_segments_table))

    arrival_name = q(args.arrival_table)
    if not spark.catalog.tableExists(arrival_name):
        schema = T.StructType([
            T.StructField("run_id", T.StringType(), False),
            T.StructField("event_id", T.StringType(), False),
            T.StructField("user_id", T.StringType(), False),
            T.StructField("trip_id", T.StringType(), False),
            T.StructField("sequence", T.LongType(), False),
            T.StructField("replay_visible_at", T.TimestampType(), False),
        ])
        spark.createDataFrame([], schema).write.format("delta").saveAsTable(arrival_name)
        print("REPLAY_TABLE_CREATED", arrival_name)
    else:
        print("REPLAY_TABLE_EXISTS", arrival_name)


if __name__ == "__main__":
    main()

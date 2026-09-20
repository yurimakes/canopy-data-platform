"""Incrementally replay one source trip as concurrent synthetic trips, then emit trip_ended rows."""

from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone

from pyspark.sql import SparkSession, types as T


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--source-table", required=True)
    p.add_argument("--replay-table", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--arrival-table", required=True)
    p.add_argument("--source-trip-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--users", type=int, default=5)
    p.add_argument("--points-per-user", type=int, default=300)
    p.add_argument("--sequences-per-batch", type=int, default=10)
    p.add_argument("--batch-interval-ms", type=int, default=1000)
    p.add_argument("--trip-end-interval-ms", type=int, default=0)
    return p.parse_args()


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    source_name = f"{args.catalog}.{args.schema}.{args.source_table}"
    replay_name = f"{args.catalog}.{args.schema}.{args.replay_table}"
    trip_end_name = f"{args.catalog}.{args.schema}.{args.trip_ended_table}"
    arrival_name = f"{args.catalog}.{args.schema}.{args.arrival_table}"

    source_df = (
        spark.table(source_name)
        .where(f"trip_id = '{args.source_trip_id}'")
        .orderBy("sequence")
        .limit(args.points_per_user)
    )
    source_rows = source_df.collect()
    if len(source_rows) != args.points_per_user:
        raise ValueError(
            f"requested {args.points_per_user} points but found {len(source_rows)} "
            f"for trip {args.source_trip_id}"
        )

    input_schema = source_df.schema
    arrival_schema = T.StructType([
        T.StructField("run_id", T.StringType(), False),
        T.StructField("event_id", T.StringType(), False),
        T.StructField("user_id", T.StringType(), False),
        T.StructField("trip_id", T.StringType(), False),
        T.StructField("sequence", T.LongType(), False),
        T.StructField("replay_visible_at", T.TimestampType(), False),
    ])

    synthetic = []
    identities = []
    for user_idx in range(args.users):
        synthetic_user = f"replay:{args.run_id}:user:{user_idx:02d}"
        synthetic_trip = f"replay:{args.run_id}:trip:{user_idx:02d}"
        identities.append((synthetic_user, synthetic_trip))
        user_rows = []
        for row in source_rows:
            values = row.asDict(recursive=True)
            values["event_id"] = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"canopy:{args.run_id}:{user_idx}:{values['event_id']}",
                )
            )
            values["user_id"] = synthetic_user
            values["trip_id"] = synthetic_trip
            user_rows.append(values)
        synthetic.append(user_rows)

    total_written = 0
    for start in range(0, args.points_per_user, args.sequences_per_batch):
        stop = min(start + args.sequences_per_batch, args.points_per_user)
        batch_rows = []
        for user_idx in range(args.users):
            batch_rows.extend(synthetic[user_idx][start:stop])

        (
            spark.createDataFrame(batch_rows, schema=input_schema)
            .write.format("delta").mode("append").saveAsTable(replay_name)
        )

        visible_at = now_utc_naive()
        arrivals = [
            {
                "run_id": args.run_id,
                "event_id": row["event_id"],
                "user_id": row["user_id"],
                "trip_id": row["trip_id"],
                "sequence": int(row["sequence"]),
                "replay_visible_at": visible_at,
            }
            for row in batch_rows
        ]
        (
            spark.createDataFrame(arrivals, schema=arrival_schema)
            .write.format("delta").mode("append").saveAsTable(arrival_name)
        )
        total_written += len(batch_rows)

        print("REPLAY_BATCH", {
            "run_id": args.run_id,
            "sequence_start": start + 1,
            "sequence_stop": stop,
            "rows": len(batch_rows),
            "total_written": total_written,
            "visible_at": str(visible_at),
        })

        if stop < args.points_per_user and args.batch_interval_ms > 0:
            time.sleep(args.batch_interval_ms / 1000.0)

    trip_end_schema = T.StructType([
        T.StructField("event_id", T.StringType(), False),
        T.StructField("event_type", T.StringType(), False),
        T.StructField("schema_version", T.StringType(), False),
        T.StructField("trip_id", T.StringType(), False),
        T.StructField("user_id", T.StringType(), False),
        T.StructField("campaign_id", T.StringType(), False),
        T.StructField("started_at", T.TimestampType(), False),
        T.StructField("ended_at", T.TimestampType(), False),
        T.StructField("expected_last_sequence", T.LongType(), False),
        T.StructField("occurred_at", T.TimestampType(), False),
        T.StructField("processing_generation", T.LongType(), False),
        T.StructField("result_owner", T.StringType(), False),
        T.StructField("event_hub_topic", T.StringType(), True),
        T.StructField("event_hub_partition", T.IntegerType(), True),
        T.StructField("event_hub_offset", T.LongType(), True),
        T.StructField("event_hub_enqueued_at", T.TimestampType(), True),
        T.StructField("bronze_ingested_at", T.TimestampType(), False),
        T.StructField("parsed_at", T.TimestampType(), False),
    ])

    first_event_time = source_rows[0]["event_time"]
    last_event_time = source_rows[-1]["event_time"]
    trip_end_times = {}

    def build_trip_end_row(user_idx, user_id, trip_id, trip_end_at):
        return {
            "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"canopy:{args.run_id}:trip_end:{user_idx}")),
            "event_type": "trip_ended",
            "schema_version": "trip-lifecycle-v1",
            "trip_id": trip_id,
            "user_id": user_id,
            "campaign_id": f"replay:{args.run_id}",
            "started_at": first_event_time,
            "ended_at": last_event_time,
            "expected_last_sequence": int(source_rows[-1]["sequence"]),
            "occurred_at": trip_end_at,
            "processing_generation": 1,
            "result_owner": "databricks",
            "event_hub_topic": None,
            "event_hub_partition": None,
            "event_hub_offset": None,
            "event_hub_enqueued_at": None,
            "bronze_ingested_at": trip_end_at,
            "parsed_at": trip_end_at,
        }

    if args.trip_end_interval_ms <= 0:
        # True simultaneous completion benchmark: one Delta append, one timestamp.
        trip_end_at = now_utc_naive()
        trip_end_rows = [
            build_trip_end_row(user_idx, user_id, trip_id, trip_end_at)
            for user_idx, (user_id, trip_id) in enumerate(identities)
        ]
        (
            spark.createDataFrame(trip_end_rows, schema=trip_end_schema)
            .write.format("delta").mode("append").saveAsTable(trip_end_name)
        )
        for user_id, trip_id in identities:
            trip_end_times[trip_id] = str(trip_end_at)
            print("TRIP_END_EMITTED", {
                "run_id": args.run_id,
                "trip_id": trip_id,
                "user_id": user_id,
                "trip_end_parsed_at": str(trip_end_at),
            })
    else:
        # Staggered completion benchmark: each trip_end is independently visible.
        for user_idx, (user_id, trip_id) in enumerate(identities):
            trip_end_at = now_utc_naive()
            trip_end_row = build_trip_end_row(
                user_idx, user_id, trip_id, trip_end_at
            )
            (
                spark.createDataFrame([trip_end_row], schema=trip_end_schema)
                .write.format("delta").mode("append").saveAsTable(trip_end_name)
            )
            trip_end_times[trip_id] = str(trip_end_at)
            print("TRIP_END_EMITTED", {
                "run_id": args.run_id,
                "trip_id": trip_id,
                "user_id": user_id,
                "trip_end_parsed_at": str(trip_end_at),
            })
            if user_idx + 1 < len(identities):
                time.sleep(args.trip_end_interval_ms / 1000.0)

    print("CONTINUOUS_REPLAY_PRODUCED", {
        "run_id": args.run_id,
        "users": args.users,
        "points_per_user": args.points_per_user,
        "rows": total_written,
        "trip_end_interval_ms": args.trip_end_interval_ms,
        "trip_end_times": trip_end_times,
        "replay_table": replay_name,
        "trip_ended_table": trip_end_name,
    })


if __name__ == "__main__":
    main()

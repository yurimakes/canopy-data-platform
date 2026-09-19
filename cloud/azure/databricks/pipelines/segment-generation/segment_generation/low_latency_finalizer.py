"""Low-latency finalized-trip segment writer driven by trip-end/prediction changes."""

from __future__ import annotations

import argparse

from pyspark.sql import SparkSession, functions as F

from segment_generation.segmentation import (
    build_ready_points,
    build_segments,
    stabilize_predictions,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--trip-ended-table", required=True)
    p.add_argument("--gps-table", required=True)
    p.add_argument("--predictions-table", required=True)
    p.add_argument("--segments-table", required=True)
    p.add_argument("--checkpoint-location", required=True)
    p.add_argument("--trigger-interval", default="1 second")
    p.add_argument("--max-repair-gap-seconds", type=int, default=3)
    return p.parse_args()


def qualify(catalog: str, schema: str, table: str) -> str:
    return f"{catalog}.{schema}.{table}"


def merge_segments(spark: SparkSession, target: str, segments, batch_id: int) -> None:
    if segments.limit(1).count() == 0:
        print("SEGMENT_FINALIZER_NO_READY_TRIPS", {"batch_id": batch_id})
        return

    view_name = f"_segment_finalizer_batch_{batch_id}"
    segments.createOrReplaceTempView(view_name)
    spark.sql(
        f"""
        MERGE INTO {target} AS target
        USING {view_name} AS source
          ON target.segment_id = source.segment_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
    ready = [r["trip_id"] for r in segments.select("trip_id").distinct().collect()]
    print("SEGMENT_FINALIZER_WRITTEN", {"batch_id": batch_id, "trip_ids": ready})


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    trip_ended_name = qualify(args.catalog, args.schema, args.trip_ended_table)
    gps_name = qualify(args.catalog, args.schema, args.gps_table)
    predictions_name = qualify(args.catalog, args.schema, args.predictions_table)
    segments_name = qualify(args.catalog, args.schema, args.segments_table)

    if not spark.catalog.tableExists(segments_name):
        raise RuntimeError(
            f"segments target {segments_name} does not exist; run the benchmark bootstrap first"
        )

    trip_end_triggers = spark.readStream.table(trip_ended_name).select("trip_id")
    prediction_triggers = spark.readStream.table(predictions_name).select("trip_id")
    triggers = trip_end_triggers.unionByName(prediction_triggers)

    def process_batch(trigger_batch, batch_id: int) -> None:
        affected = (
            trigger_batch.where(F.col("trip_id").isNotNull())
            .select("trip_id")
            .distinct()
            .cache()
        )
        try:
            if affected.limit(1).count() == 0:
                return

            trip_ended = spark.table(trip_ended_name).join(affected, "trip_id", "semi")
            gps = spark.table(gps_name).join(affected, "trip_id", "semi")
            predictions = spark.table(predictions_name).join(affected, "trip_id", "semi")

            ready = build_ready_points(trip_ended, gps, predictions)
            stabilized = stabilize_predictions(ready, args.max_repair_gap_seconds)
            segments = build_segments(stabilized)
            merge_segments(spark, segments_name, segments, batch_id)
        finally:
            affected.unpersist()

    query = (
        triggers.writeStream.foreachBatch(process_batch)
        .option("checkpointLocation", args.checkpoint_location)
        .trigger(processingTime=args.trigger_interval)
        .queryName("canopy_low_latency_segment_finalizer")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()

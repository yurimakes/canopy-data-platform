"""Read existing ML tables; persist bounded waits and immutable finalizer inputs.

No writes to ML tables, no new pipeline, no ML completion signal required.
The caller runs this bounded task periodically. Spark handles Trips as DataFrames.
"""
import argparse
from datetime import datetime, timezone

KEYS = ["user_id", "trip_id", "processing_generation"]


def assess(ends, gps, predictions):
    """Require all GPS receipts and coverage of every usable point, including the tail.

    GPS distance belongs to the transition ENDING at that point. A shared boundary
    is assigned once to the earlier prediction; strictly overlapping windows block.
    Invalid transitions are excluded rather than silently counted as travel.
    """
    from pyspark.sql import functions as F, Window
    g = gps.dropDuplicates().alias("g")
    e = ends.alias("e")
    points = e.join(g, (F.col("e.user_id") == F.col("g.user_id")) &
                    (F.col("e.trip_id") == F.col("g.trip_id")) &
                    F.col("g.sequence").between(1, F.col("e.expected_last_sequence")), "inner").select(
        *[F.col("e." + k).alias(k) for k in KEYS],
        *[F.col("g." + k).alias(k) for k in ("event_id", "sequence", "event_time", "distance_m", "transition_valid")])
    counts = points.groupBy(*KEYS).agg(F.count("sequence").alias("point_rows"),
        F.countDistinct("sequence").alias("sequence_count"), F.countDistinct("event_id").alias("event_count"),
        F.min("event_time").alias("first_gps_time"), F.max("event_time").alias("last_gps_time"))
    p = predictions.dropDuplicates().alias("p")
    scoped = e.join(p, (F.col("e.user_id") == F.col("p.user_id")) &
                      (F.col("e.trip_id") == F.col("p.trip_id")), "inner").select(
        *[F.col("e." + k).alias(k) for k in KEYS],
        *[F.col("p." + k).alias(k) for k in ("segment_id", "start_time", "end_time", "strong_mode",
                "strong_confidence", "inference_status", "model_uri")], "e.started_at", "e.ended_at")
    timeline = Window.partitionBy(*KEYS).orderBy("start_time", "end_time", "segment_id")
    prior = timeline.rowsBetween(Window.unboundedPreceding, -1)
    scoped = scoped.withColumn("prior_end", F.max("end_time").over(prior))
    valid = (F.col("inference_status") == "scored") & F.col("strong_mode").isin("walk", "bike", "car", "bus", "rail", "train") & (
        F.col("strong_confidence").between(0, 1)) & (F.length(F.trim("model_uri")) > 0) & (
        F.col("end_time") >= F.col("start_time")) & (F.col("start_time") >= F.col("started_at")) & (
        F.col("end_time") <= F.col("ended_at"))
    summary = scoped.groupBy(*KEYS).agg(F.count("segment_id").alias("prediction_rows"),
        F.countDistinct("segment_id").alias("prediction_ids"),
        F.sum(F.when(F.coalesce(valid, F.lit(False)), 0).otherwise(1)).alias("bad_predictions"),
        F.sum(F.when(F.col("start_time") < F.col("prior_end"), 1).otherwise(0)).alias("overlaps"),
        F.countDistinct("model_uri").alias("model_versions"), F.first("model_uri").alias("model_version"))
    usable = points.where(F.col("transition_valid") & (F.col("sequence") > 1)).alias("g")
    candidates = scoped.where(valid).alias("p")
    matched = usable.join(candidates, [*KEYS], "inner").where(
        F.col("g.event_time").between(F.col("p.start_time"), F.col("p.end_time"))).select(
        *[F.col(k) for k in KEYS], "g.event_id", "g.sequence", "g.event_time", "g.distance_m",
        "p.segment_id", "p.start_time", "p.end_time", "p.strong_mode", "p.strong_confidence")
    choice = Window.partitionBy(*KEYS, "sequence").orderBy("start_time", "end_time", "segment_id")
    assigned = matched.withColumn("choice", F.row_number().over(choice)).where("choice=1")
    needed = usable.groupBy(*KEYS).agg(F.count("sequence").alias("needed_points"),
        F.sum(F.when(F.col("distance_m").isNull() | F.isnan("distance_m") |
                     (F.abs("distance_m") == float("inf")) | (F.col("distance_m") < 0), 1).otherwise(0)).alias("bad_distances"))
    coverage = assigned.groupBy(*KEYS).agg(F.count("sequence").alias("covered_points"),
                                          F.max("event_time").alias("last_covered_time"))
    segment = assigned.groupBy(*KEYS, "segment_id", "start_time", "end_time", "strong_mode", "strong_confidence").agg(
        F.sum("distance_m").alias("distance_m"))
    segment = segment.withColumn("mode", F.when(F.col("strong_mode") == "train", "rail").otherwise(F.col("strong_mode")))
    arrays = segment.groupBy(*KEYS).agg(F.sort_array(F.collect_list(F.struct(
        "start_time", "end_time", "segment_id", "mode", "distance_m", F.col("strong_confidence").alias("confidence")))).alias("segments"))
    out = ends.join(counts, KEYS, "left").join(summary, KEYS, "left").join(needed, KEYS, "left").join(
        coverage, KEYS, "left").join(arrays, KEYS, "left").fillna(0, subset=["point_rows", "sequence_count", "event_count",
        "prediction_rows", "prediction_ids", "bad_predictions", "overlaps", "model_versions", "needed_points", "covered_points", "bad_distances"])
    reason = (F.when(F.col("result_owner") != "databricks", "functions_owned")
        .when(F.col("expected_last_sequence") <= 0, "no_gps")
        .when((F.col("point_rows") != F.col("sequence_count")) | (F.col("event_count") != F.col("sequence_count")), "conflicting_gps")
        .when(F.col("sequence_count") != F.col("expected_last_sequence"), "waiting_for_gps")
        .when((F.col("first_gps_time") < F.col("started_at")) | (F.col("last_gps_time") > F.col("ended_at")), "invalid_gps_times")
        .when(F.col("bad_distances") > 0, "invalid_distance")
        .when(F.col("prediction_rows") != F.col("prediction_ids"), "conflicting_predictions")
        .when(F.col("overlaps") > 0, "overlapping_predictions")
        .when(F.col("bad_predictions") > 0, "waiting_for_scored_predictions")
        .when(F.col("model_versions") > 1, "mixed_model_versions")
        .when((F.col("needed_points") == 0) | (F.col("covered_points") != F.col("needed_points")) |
              (F.col("last_covered_time") != F.col("last_gps_time")) | F.col("last_covered_time").isNull(), "waiting_for_prediction_coverage")
        .otherwise("ready"))
    return out.withColumn("reason", reason)


def advance(assessed, now, max_attempts=12):
    """Only poll due rows; expired rows never finalize even if late data appeared."""
    from pyspark.sql import functions as F
    instant = F.lit(now).cast("timestamp")
    out = assessed.withColumn("attempts", F.col("attempts") + 1)
    expired = (instant >= F.col("deadline_at")) | ((F.col("attempts") >= max_attempts) & (F.col("reason") != "ready"))
    out = out.withColumn("status", F.when(F.col("reason") == "functions_owned", "ignored")
        .when(F.col("reason") == "no_gps", "failed").when(expired, "timed_out")
        .when(F.col("reason") == "ready", "ready").otherwise("waiting"))
    delay = F.least(F.lit(60), F.lit(10) * F.pow(F.lit(2), F.least(F.col("attempts") - 1, F.lit(3)))).cast("long")
    out = out.withColumn("next_check_at", F.timestamp_micros(F.unix_micros(instant) + delay * 1000000)).withColumn("checked_at", instant)
    trip = F.struct("trip_id", "user_id", "campaign_id", "started_at", "ended_at", "processing_generation",
                    F.lit("processing").alias("status"))
    result = F.struct("trip_id", "model_version", "segments")
    return out.withColumn("envelope_json", F.when(F.col("status") == "ready", F.to_json(F.struct(
        F.lit("external").alias("provider"), trip.alias("trip"), result.alias("result"), instant.alias("completed_at")))))


def register(spark, ends, queue_path, now, timeout_seconds=600):
    """First receipt starts the deadline; replay must never reset it."""
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F, Window
    instant = F.lit(now).cast("timestamp")
    fields = [*KEYS, "event_id", "campaign_id", "started_at", "ended_at", "expected_last_sequence", "result_owner"]
    unique = ends.select(*fields).dropDuplicates()
    grouped = Window.partitionBy(*KEYS)
    unique = unique.withColumn("variants", F.count("event_id").over(grouped)).withColumn(
        "pick", F.row_number().over(grouped.orderBy(F.to_json(F.struct(*fields))))).where("pick=1")
    valid = (F.col("expected_last_sequence").between(0, 10000000)) & (F.col("processing_generation") >= 1) & (
        F.col("ended_at") >= F.col("started_at")) & F.col("result_owner").isin("functions", "databricks")
    for key in ("user_id", "trip_id", "event_id", "campaign_id"):
        valid = valid & (F.length(F.trim(F.col(key))) > 0)
    rows = unique.withColumn("status", F.when((F.col("variants") != 1) | ~F.coalesce(valid, F.lit(False)), "failed").otherwise("waiting"))
    rows = rows.withColumn("reason", F.when(F.col("variants") != 1, "conflicting_end_events")
                           .when(F.col("status") == "failed", "invalid_end_event").otherwise("not_checked")).drop("variants", "pick").withColumn(
        "attempts", F.lit(0)).withColumn("first_seen_at", instant).withColumn("next_check_at", instant).withColumn(
        "deadline_at", F.timestamp_micros(F.unix_micros(instant) + timeout_seconds * 1000000)).withColumn(
        "checked_at", F.lit(None).cast("timestamp")).withColumn("envelope_json", F.lit(None).cast("string")).withColumn(
        "retry_request_id", F.lit(None).cast("string"))
    if not DeltaTable.isDeltaTable(spark, queue_path):
        rows.write.format("delta").mode("error").save(queue_path)
    else:
        target = DeltaTable.forPath(spark, queue_path)
        same = F.struct(*[F.col("t."+k) for k in fields]).eqNullSafe(F.struct(*[F.col("s."+k) for k in fields]))
        target.alias("t").merge(rows.alias("s"), " AND ".join("t."+k+"=s."+k for k in KEYS)).whenMatchedUpdate(
            condition=(F.col("t.status") == "waiting") & (~same | (F.col("s.status") == "failed")),
            set={"status": F.lit("failed"), "reason": F.lit("conflicting_end_events")}).whenNotMatchedInsertAll().execute()


def poll(spark, queue_path, gps_table, prediction_table, now, max_attempts=12):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    target = DeltaTable.forPath(spark, queue_path)
    due = target.toDF().where((F.col("status") == "waiting") & (F.col("next_check_at") <= F.lit(now)))
    if not due.limit(1).count():
        return
    # Keep updates bounded to our Delta queue. ML tables are read-only inputs.
    columns = target.toDF().columns
    try:
        updated = advance(assess(due, spark.table(gps_table), spark.table(prediction_table)), now, max_attempts)
        changes = updated.select(*columns)
        changes.count()
    except Exception:
        # Serverless does not support DataFrame cache. Delta MERGE materializes its source.
        empty_segments = "array<struct<start_time:timestamp,end_time:timestamp,segment_id:string,mode:string,distance_m:double,confidence:double>>"
        failed_read = due.withColumn("reason", F.lit("source_read_failed")).withColumn(
            "model_version", F.lit(None).cast("string")).withColumn("segments", F.lit(None).cast(empty_segments))
        changes = advance(failed_read, now, max_attempts).select(*columns)
    condition = " AND ".join("t."+k+"=s."+k for k in KEYS)
    target.alias("t").merge(changes.alias("s"), condition).whenMatchedUpdateAll(
        condition="t.status='waiting' AND t.attempts=s.attempts-1 AND t.retry_request_id <=> s.retry_request_id").execute()


def retry(spark, queue_path, user_id, trip_id, generation, request_id, now, timeout_seconds=600):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    if not request_id or not request_id.strip():
        raise ValueError("retry request ID is required")
    target = DeltaTable.forPath(spark, queue_path)
    condition = ((F.col("user_id") == user_id) & (F.col("trip_id") == trip_id) &
                 (F.col("processing_generation") == generation) & (F.col("status") == "timed_out") &
                 (~F.col("retry_request_id").eqNullSafe(F.lit(request_id))))
    instant = F.lit(now).cast("timestamp")
    target.update(condition, {"status": F.lit("waiting"), "reason": F.lit("manual_retry"), "attempts": F.lit(0),
        "next_check_at": instant, "deadline_at": F.timestamp_micros(F.unix_micros(instant) + timeout_seconds * 1000000),
        "retry_request_id": F.lit(request_id)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("register", "poll", "retry"))
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--end-table")
    parser.add_argument("--gps-table", default="dbw_canopy_dev.silver.gps_features")
    parser.add_argument("--prediction-table", default="dbw_canopy_dev.gold.mode_segment_predictions")
    parser.add_argument("--user-id")
    parser.add_argument("--trip-id")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=12)
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.max_attempts <= 0:
        parser.error("timeout and max attempts must be positive")
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    now = datetime.now(timezone.utc)
    if args.phase == "register":
        if not args.end_table:
            parser.error("--end-table is required (existing routed lifecycle Delta table)")
        register(spark, spark.table(args.end_table), args.queue_path, now, args.timeout_seconds)
    elif args.phase == "poll":
        poll(spark, args.queue_path, args.gps_table, args.prediction_table, now, args.max_attempts)
    else:
        if not all((args.user_id, args.trip_id, args.generation, args.request_id)):
            parser.error("retry requires --user-id, --trip-id, --generation and --request-id")
        retry(spark, args.queue_path, args.user_id, args.trip_id, args.generation, args.request_id, now, args.timeout_seconds)


if __name__ == "__main__":
    main()

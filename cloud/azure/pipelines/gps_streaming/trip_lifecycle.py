"""DataFrame-only Trip end ingestion and fail-closed finalization readiness."""
END_SCHEMA = """event_id string, event_type string, schema_version string, user_id string,
trip_id string, campaign_id string, started_at timestamp, ended_at timestamp,
expected_last_sequence long, occurred_at timestamp, processing_generation long, result_owner string"""
ML_COMPLETION_SCHEMA = """user_id string, trip_id string, processing_generation long,
processed_last_sequence long, processed_sequence_count long, segments_finalized boolean,
model_version string"""


def parse_end_events(bronze):
    from pyspark.sql import functions as F
    ends = bronze.where(F.get_json_object("body", "$.event_type") == "trip_ended")
    parsed = ends.select("body", "event_hub_enqueued_at", "ingested_at",
                         F.from_json("body", END_SCHEMA).alias("e")).select("body", "event_hub_enqueued_at", "ingested_at", "e.*")
    valid = (F.col("schema_version") == "trip-lifecycle-v1") & (F.col("expected_last_sequence").between(0, 10000000)) & (
        F.col("processing_generation") >= 1) & F.col("result_owner").isin("functions", "databricks") & (
        F.col("ended_at") >= F.col("started_at")) & (F.col("occurred_at").isNotNull())
    for key in ("event_id", "user_id", "trip_id", "campaign_id"):
        valid = valid & (F.length(F.trim(F.col(key))) > 0)
    return parsed.withColumn("valid", F.coalesce(valid, F.lit(False)))


def finalization_status(ends, bronze, ml_completions):
    """One row per user/Trip/generation; max(sequence) alone never proves completeness.

    ML completion is an explicit upstream contract: processed_sequence_count is the
    count of DISTINCT sequences fully handled (including intentionally rejected GPS),
    and segments_finalized acknowledges flushing the last open segment. No ack = wait.
    """
    from pyspark.sql import functions as F
    keys = ["user_id", "trip_id", "processing_generation"]
    payload = ["event_id", "campaign_id", "started_at", "ended_at", "expected_last_sequence", "result_owner"]
    end = ends.groupBy(*keys).agg(
        F.countDistinct(F.struct(*payload)).alias("end_variants"),
        *[F.first(key).alias(key) for key in payload])
    gps_schema = "user_id string, trip_id string, event_id string, sequence long"
    gps = bronze.where(F.coalesce(F.get_json_object("body", "$.event_type"), F.lit("gps")) == "gps").select(
        F.from_json("body", gps_schema).alias("g")).select("g.*").where(
        F.col("sequence").between(1, 10000000) & F.col("event_id").isNotNull())
    bounded = end.select(*keys, "expected_last_sequence").join(gps, ["user_id", "trip_id"], "left").where(
        F.col("sequence").isNull() | (F.col("sequence") <= F.col("expected_last_sequence")))
    counts = bounded.groupBy(*keys).agg(F.countDistinct("sequence").alias("gps_sequence_count"),
                                       F.countDistinct("event_id").alias("gps_event_count"))
    ack = ml_completions.groupBy(*keys).agg(
        F.countDistinct(F.struct("processed_last_sequence", "processed_sequence_count", "segments_finalized", "model_version")).alias("ml_variants"),
        *[F.first(key).alias(key) for key in ("processed_last_sequence", "processed_sequence_count", "segments_finalized", "model_version")])
    result = end.join(counts, keys, "left").join(ack, keys, "left").fillna({"gps_sequence_count": 0, "gps_event_count": 0})
    result = result.withColumn("gps_complete", (F.col("gps_sequence_count") == F.col("expected_last_sequence")) &
                              (F.col("gps_event_count") == F.col("expected_last_sequence")))
    result = result.withColumn("segments_complete", F.coalesce((F.col("ml_variants") == 1) &
        (F.col("processed_last_sequence") == F.col("expected_last_sequence")) &
        (F.col("processed_sequence_count") == F.col("expected_last_sequence")) &
        F.col("segments_finalized") & (F.length(F.trim(F.col("model_version"))) > 0), F.lit(False)))
    reason = (F.when(F.col("end_variants") != 1, "conflicting_end_events")
              .when(F.col("result_owner") != "databricks", "mock_functions_owner")
              .when(F.col("expected_last_sequence") == 0, "no_gps")
              .when(~F.col("gps_complete"), "waiting_for_gps")
              .when(~F.col("segments_complete"), "waiting_for_segments")
              .otherwise("ready_to_finalize"))
    return result.withColumn("finalization_status", reason).withColumn("can_finalize", F.col("finalization_status") == "ready_to_finalize")

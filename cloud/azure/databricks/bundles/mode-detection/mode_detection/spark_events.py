"""Normalize Silver GPS and trip-end streams into one keyed event stream."""

from __future__ import annotations


def gps_events(observations):
    from pyspark.sql import functions as F

    return observations.select(
        F.lit("gps").alias("event_kind"),
        "event_id",
        "trip_id",
        "user_id",
        "sequence",
        "event_time",
        "lat",
        "lon",
        "accuracy",
        "altitude_m",
        F.lit(None).cast("string").alias("campaign_id"),
        F.lit(None).cast("timestamp").alias("started_at"),
        F.lit(None).cast("timestamp").alias("ended_at"),
        F.lit(None).cast("long").alias("expected_last_sequence"),
        F.lit(None).cast("timestamp").alias("occurred_at"),
        F.lit(None).cast("long").alias("processing_generation"),
        F.lit(None).cast("string").alias("result_owner"),
    )


def trip_end_events(trip_ends):
    from pyspark.sql import functions as F

    return trip_ends.select(
        F.lit("trip_end").alias("event_kind"),
        "event_id",
        "trip_id",
        "user_id",
        F.lit(None).cast("long").alias("sequence"),
        F.lit(None).cast("timestamp").alias("event_time"),
        F.lit(None).cast("double").alias("lat"),
        F.lit(None).cast("double").alias("lon"),
        F.lit(None).cast("double").alias("accuracy"),
        F.lit(None).cast("double").alias("altitude_m"),
        "campaign_id",
        "started_at",
        "ended_at",
        "expected_last_sequence",
        "occurred_at",
        "processing_generation",
        "result_owner",
    )


def unified_events(observations, trip_ends):
    return gps_events(observations).unionByName(trip_end_events(trip_ends))

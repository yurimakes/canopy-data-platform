"""Normalize prediction and lifecycle inputs to a tagged union stream."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .state_machine import PredictionPoint, TripEnd


def _value(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, Mapping) else getattr(row, name)


def event_from_row(row: Any) -> PredictionPoint | TripEnd:
    kind = _value(row, "event_kind")
    if kind == "prediction":
        return PredictionPoint(
            event_id=str(_value(row, "event_id")),
            user_id=str(_value(row, "user_id")),
            trip_id=str(_value(row, "trip_id")),
            sequence=int(_value(row, "sequence")),
            event_time=_value(row, "event_time"),
            lat=float(_value(row, "lat")),
            lon=float(_value(row, "lon")),
            predicted_mode=str(_value(row, "predicted_mode")),
            confidence=(
                None if _value(row, "confidence") is None else float(_value(row, "confidence"))
            ),
            model_name=str(_value(row, "model_name")),
            model_version=(
                None if _value(row, "model_version") is None else str(_value(row, "model_version"))
            ),
            predicted_at=_value(row, "predicted_at"),
        )
    if kind == "trip_end":
        return TripEnd(
            event_id=str(_value(row, "event_id")),
            trip_id=str(_value(row, "trip_id")),
            user_id=str(_value(row, "user_id")),
            expected_last_sequence=int(_value(row, "expected_last_sequence")),
            processing_generation=int(_value(row, "processing_generation")),
            parsed_at=_value(row, "trip_end_parsed_at"),
            result_owner=str(_value(row, "result_owner")),
        )
    raise ValueError(f"unsupported event_kind: {kind!r}")


def prediction_events(predictions: Any) -> Any:
    from pyspark.sql import functions as F

    return predictions.select(
        F.lit("prediction").alias("event_kind"),
        "event_id", "user_id", "trip_id", "sequence", "event_time", "lat", "lon",
        "predicted_mode", "confidence", "model_name", "model_version", "predicted_at",
        F.lit(None).cast("long").alias("expected_last_sequence"),
        F.lit(None).cast("long").alias("processing_generation"),
        F.lit(None).cast("timestamp").alias("trip_end_parsed_at"),
        F.lit(None).cast("string").alias("result_owner"),
    )


def trip_end_events(trip_ends: Any) -> Any:
    from pyspark.sql import functions as F

    return trip_ends.select(
        F.lit("trip_end").alias("event_kind"),
        "event_id", "user_id", "trip_id",
        F.lit(None).cast("long").alias("sequence"),
        F.lit(None).cast("timestamp").alias("event_time"),
        F.lit(None).cast("double").alias("lat"),
        F.lit(None).cast("double").alias("lon"),
        F.lit(None).cast("string").alias("predicted_mode"),
        F.lit(None).cast("double").alias("confidence"),
        F.lit(None).cast("string").alias("model_name"),
        F.lit(None).cast("string").alias("model_version"),
        F.lit(None).cast("timestamp").alias("predicted_at"),
        "expected_last_sequence", "processing_generation",
        F.col("parsed_at").alias("trip_end_parsed_at"),
        "result_owner",
    )


def unified_events(predictions: Any, trip_ends: Any) -> Any:
    return prediction_events(predictions).unionByName(trip_end_events(trip_ends))

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from integrated_mode_segmentation.events import event_from_row
from integrated_mode_segmentation.state_machine import PredictionPoint, TripEnd


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def test_prediction_union_row_converts_to_enriched_point() -> None:
    event = event_from_row(
        {
            "event_kind": "prediction",
            "event_id": "p1",
            "user_id": "u1",
            "trip_id": "t1",
            "sequence": 1,
            "event_time": NOW,
            "lat": 37.1,
            "lon": 127.1,
            "predicted_mode": "walk",
            "confidence": None,
            "model_name": "m",
            "model_version": "1",
            "predicted_at": NOW,
            "expected_last_sequence": None,
            "processing_generation": None,
            "trip_end_parsed_at": None,
            "result_owner": None,
        }
    )
    assert event == PredictionPoint(
        "p1", "u1", "t1", 1, NOW, 37.1, 127.1, "walk", None, "m", "1", NOW
    )


def test_trip_end_union_row_converts_to_completion_event() -> None:
    event = event_from_row(
        {
            "event_kind": "trip_end",
            "event_id": "e1",
            "user_id": "u1",
            "trip_id": "t1",
            "sequence": None,
            "event_time": None,
            "lat": None,
            "lon": None,
            "predicted_mode": None,
            "confidence": None,
            "model_name": None,
            "model_version": None,
            "predicted_at": None,
            "expected_last_sequence": 4,
            "processing_generation": 2,
            "trip_end_parsed_at": NOW,
            "result_owner": "databricks",
        }
    )
    assert event == TripEnd("e1", "t1", "u1", 4, 2, NOW, "databricks")


def test_unknown_union_discriminator_is_rejected() -> None:
    with pytest.raises(ValueError, match="event_kind"):
        event_from_row({"event_kind": "mystery"})


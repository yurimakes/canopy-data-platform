from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mode_detection.contract import ModeModelMetadata, ModePrediction
from mode_detection.segmentation import SegmentState
from mode_detection.transit import TransitAdjustedPrediction


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
META = ModeModelMetadata("fake", "1", "test", 120, 10)


def adjusted(seconds: int, mode: str, confidence: float = 0.8):
    raw = ModePrediction(
        predicted_mode=mode,
        confidence=confidence,
        probabilities={mode: confidence},
        window_start=BASE + timedelta(seconds=seconds - 120),
        window_end=BASE + timedelta(seconds=seconds),
        metadata=META,
    )
    return TransitAdjustedPrediction(
        raw_prediction=raw,
        final_mode=mode,
        confidence=confidence,
        decision_status="unchanged",
        correction_applied=False,
        correction_reason="",
        context={},
    )


def test_first_prediction_labels_initial_trip_history():
    state = SegmentState(BASE)
    state.apply(adjusted(120, "bus"))

    assert state.segments[0].mode == "bus"
    assert state.segments[0].start_time == BASE
    assert state.segments[0].end_time == BASE + timedelta(seconds=120)


def test_same_mode_predictions_extend_current_segment():
    state = SegmentState(BASE)
    state.apply(adjusted(120, "bus", 0.9))
    state.apply(adjusted(130, "bus", 0.7))

    segment = state.segments[0]
    assert segment.start_time == BASE
    assert segment.end_time == BASE + timedelta(seconds=130)
    assert segment.confidence == pytest.approx(0.7)
    assert segment.prediction_count == 2


def test_mode_change_occurs_at_new_prediction_window_end():
    state = SegmentState(BASE)
    state.apply(adjusted(120, "bus"))
    state.apply(adjusted(130, "bus"))
    state.apply(adjusted(140, "walk"))

    assert [(s.mode, s.start_time, s.end_time) for s in state.segments] == [
        ("bus", BASE, BASE + timedelta(seconds=140)),
        (
            "walk",
            BASE + timedelta(seconds=140),
            BASE + timedelta(seconds=140),
        ),
    ]


def test_predictions_must_arrive_in_time_order():
    state = SegmentState(BASE)
    state.apply(adjusted(120, "bus"))
    with pytest.raises(ValueError, match="strictly increasing"):
        state.apply(adjusted(120, "walk"))

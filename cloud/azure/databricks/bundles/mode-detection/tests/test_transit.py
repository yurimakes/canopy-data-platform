from __future__ import annotations

from datetime import datetime, timezone

from mode_detection.contract import (
    ModeModelMetadata,
    ModePrediction,
    Observation,
)
from mode_detection.transit import TransitContextState


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
META = ModeModelMetadata("fake", "1", "test", 120, 10)


def prediction(mode="bus"):
    return ModePrediction(
        predicted_mode=mode,
        confidence=0.6,
        probabilities={"walk": 0.1, "bus": 0.6, "rail": 0.3},
        window_start=NOW,
        window_end=NOW,
        metadata=META,
    )


def observations():
    return [
        Observation(1, NOW, 37.0, 127.0, 5.0, 10.0),
        Observation(2, NOW, 37.1, 127.1, 5.0, 10.0),
    ]


def test_transit_adjustment_preserves_raw_prediction_and_corrects_mode():
    def resolver(probabilities, points, station_history):
        assert probabilities["bus"] == 0.6
        assert station_history == ()
        return (
            {
                "final_mode": "rail",
                "decision_confidence": 0.85,
                "decision_status": "corrected",
                "correction_applied": True,
                "correction_reason": "ordered subway evidence",
            },
            {
                "matched_subway_line": "2",
                "subway_current_observed_station_ids": ["201", "202"],
            },
        )

    state = TransitContextState()
    adjusted = state.apply(
        prediction(),
        observations(),
        resolver=resolver,
    )

    assert adjusted.raw_prediction.predicted_mode == "bus"
    assert adjusted.final_mode == "rail"
    assert adjusted.confidence == 0.85
    assert adjusted.correction_applied is True


def test_subway_station_history_accumulates_without_duplicates():
    histories = []

    def resolver(_probabilities, _points, station_history):
        histories.append(station_history)
        return (
            {
                "final_mode": "rail",
                "decision_confidence": 0.9,
                "decision_status": "confirmed",
                "correction_applied": False,
                "correction_reason": "rail retained",
            },
            {
                "matched_subway_line": "2",
                "subway_current_observed_station_ids": ["201", "202"],
            },
        )

    state = TransitContextState()
    state.apply(prediction("rail"), observations(), resolver=resolver)
    state.apply(prediction("rail"), observations(), resolver=resolver)

    assert histories[0] == ()
    assert histories[1] == (("201", "2"), ("202", "2"))
    assert state.station_history == [("201", "2"), ("202", "2")]


def test_non_subway_context_does_not_pollute_station_history():
    def resolver(_probabilities, _points, _station_history):
        return (
            {
                "final_mode": "bus",
                "decision_confidence": 0.7,
                "decision_status": "unchanged",
                "correction_applied": False,
                "correction_reason": "ML prediction retained",
            },
            {
                "matched_subway_line": None,
                "subway_current_observed_station_ids": ["201"],
            },
        )

    state = TransitContextState()
    state.apply(prediction(), observations(), resolver=resolver)
    assert state.station_history == []

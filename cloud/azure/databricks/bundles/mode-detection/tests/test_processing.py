from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mode_detection.contract import ModeModelMetadata, ModePrediction, Observation
from mode_detection.processing import ModeDetectionProcessor


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(sequence, seconds):
    return Observation(
        sequence=sequence,
        event_time=BASE + timedelta(seconds=seconds),
        lat=37.0,
        lon=127.0 + sequence * 0.00001,
        accuracy_m=5.0,
        altitude_m=10.0,
    )


class FakeModel:
    def __init__(self):
        self._metadata = ModeModelMetadata("fake", "1", "test", 120, 10)

    @property
    def metadata(self):
        return self._metadata

    def prediction_ready(self, observations, *, window_end):
        start = window_end - timedelta(seconds=120)
        points = [p for p in observations if start <= p.event_time <= window_end]
        return bool(points) and points[0].event_time <= start and points[-1].event_time >= window_end

    def predict(self, observations, *, window_end, raw_point_count):
        mode = "bus" if window_end < BASE + timedelta(seconds=140) else "walk"
        return ModePrediction(
            predicted_mode=mode,
            confidence=0.8,
            probabilities={"bus": 0.8 if mode == "bus" else 0.2, "walk": 0.2 if mode == "bus" else 0.8},
            window_start=window_end - timedelta(seconds=120),
            window_end=window_end,
            metadata=self.metadata,
        )


def transit_resolver(probabilities, _points, _history):
    mode = max(probabilities, key=probabilities.get)
    return (
        {
            "final_mode": mode,
            "decision_confidence": probabilities[mode],
            "decision_status": "unchanged",
            "correction_applied": False,
            "correction_reason": "ML prediction retained",
        },
        {},
    )


def test_processor_builds_segments_while_draining_predictions():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    processor.trip.add_observations(
        observation(i + 1, sec) for i, sec in enumerate(range(0, 141))
    )

    updates = processor.drain_due_mode_updates(
        FakeModel(),
        raw_point_count_for_window=lambda _start, _end, points: len(points),
        transit_resolver=transit_resolver,
    )

    assert [u.final_mode for u in updates] == ["bus", "bus", "walk"]
    assert [(s.mode, s.start_time, s.end_time) for s in processor.segments.segments] == [
        ("bus", BASE, BASE + timedelta(seconds=140)),
        ("walk", BASE + timedelta(seconds=140), BASE + timedelta(seconds=140)),
    ]


def test_transit_corrected_mode_is_what_segmentation_consumes():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    processor.trip.add_observations(
        observation(i + 1, sec) for i, sec in enumerate(range(0, 121))
    )

    def correct_to_rail(_probabilities, _points, _history):
        return (
            {
                "final_mode": "rail",
                "decision_confidence": 0.9,
                "decision_status": "corrected",
                "correction_applied": True,
                "correction_reason": "subway evidence",
            },
            {
                "matched_subway_line": "2",
                "subway_current_observed_station_ids": ["201", "202"],
            },
        )

    processor.drain_due_mode_updates(
        FakeModel(),
        raw_point_count_for_window=lambda _start, _end, points: len(points),
        transit_resolver=correct_to_rail,
    )

    assert processor.segments.segments[0].mode == "rail"
    assert processor.transit.station_history == [("201", "2"), ("202", "2")]


def test_processor_skips_unusable_window_and_recovers_later_predictions():
    class GapModel(FakeModel):
        def prediction_ready(self, observations, *, window_end):
            if window_end == BASE + timedelta(seconds=130):
                return False
            return super().prediction_ready(observations, window_end=window_end)

    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    processor.trip.add_observations(
        observation(i + 1, sec) for i, sec in enumerate(range(0, 141))
    )

    updates = processor.drain_due_mode_updates(
        GapModel(),
        raw_point_count_for_window=lambda _start, _end, points: len(points),
        transit_resolver=transit_resolver,
    )

    assert [u.raw_prediction.window_end for u in updates] == [
        BASE + timedelta(seconds=120),
        BASE + timedelta(seconds=140),
    ]
    assert processor.skipped_prediction_windows == 1
    assert processor.trip.last_prediction_end == BASE + timedelta(seconds=140)
    assert [(s.mode, s.start_time, s.end_time) for s in processor.segments.segments] == [
        ("bus", BASE, BASE + timedelta(seconds=120)),
        ("walk", BASE + timedelta(seconds=140), BASE + timedelta(seconds=140)),
    ]


def test_processor_isolates_prediction_value_error_and_continues():
    class RaisingModel(FakeModel):
        def predict(self, observations, *, window_end, raw_point_count):
            if window_end == BASE + timedelta(seconds=130):
                raise ValueError("bad per-window input")
            return super().predict(
                observations,
                window_end=window_end,
                raw_point_count=raw_point_count,
            )

    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    processor.trip.add_observations(
        observation(i + 1, sec) for i, sec in enumerate(range(0, 141))
    )

    updates = processor.drain_due_mode_updates(
        RaisingModel(),
        raw_point_count_for_window=lambda _start, _end, points: len(points),
        transit_resolver=transit_resolver,
    )

    assert [u.raw_prediction.window_end for u in updates] == [
        BASE + timedelta(seconds=120),
        BASE + timedelta(seconds=140),
    ]
    assert processor.skipped_prediction_windows == 1
    assert processor.trip.last_prediction_end == BASE + timedelta(seconds=140)

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mode_detection.contract import ModeModelMetadata, ModePrediction, Observation
from mode_detection.lifecycle import TripEnded, TripLifecycleState
from mode_detection.processing import ModeDetectionProcessor


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(sequence: int, seconds: int) -> Observation:
    return Observation(
        sequence=sequence,
        event_time=BASE + timedelta(seconds=seconds),
        lat=37.0,
        lon=127.0 + sequence * 0.00001,
        accuracy_m=5.0,
        altitude_m=10.0,
    )


class FakeModel:
    def __init__(self, mode="bus"):
        self._metadata = ModeModelMetadata("fake", "1", "test", 120, 10)
        self.mode = mode

    @property
    def metadata(self):
        return self._metadata

    def prediction_ready(self, observations, *, window_end):
        start = window_end - timedelta(seconds=120)
        points = [p for p in observations if start <= p.event_time <= window_end]
        return (
            len(points) >= 2
            and points[0].event_time <= start
            and points[-1].event_time >= window_end
        )

    def predict(self, observations, *, window_end, raw_point_count):
        return ModePrediction(
            predicted_mode=self.mode,
            confidence=0.8,
            probabilities={self.mode: 0.8, "walk": 0.2},
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


def raw_count(_start, _end, points):
    return len(points)


def trip_end(*, ended_seconds: int, expected_last_sequence: int, generation: int = 1):
    return TripEnded(
        event_id="event-1",
        trip_id="trip-1",
        user_id="user-1",
        campaign_id="campaign-1",
        started_at=BASE,
        ended_at=BASE + timedelta(seconds=ended_seconds),
        expected_last_sequence=expected_last_sequence,
        occurred_at=BASE + timedelta(seconds=ended_seconds),
        processing_generation=generation,
        result_owner="mode-detection",
    )


def test_sequence_completeness_survives_observation_pruning():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    model = FakeModel()
    processor.trip.add_observations(
        observation(i + 1, sec)
        for i, sec in enumerate(range(0, 141))
    )
    processor.drain_due_mode_updates(
        model,
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )

    assert processor.trip.observations[0].event_time == BASE + timedelta(seconds=30)
    assert processor.trip.has_complete_sequence_through(141)


def test_trip_end_waits_until_expected_last_sequence_is_present():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    lifecycle = TripLifecycleState()
    lifecycle.register_trip_end(
        trip_end(ended_seconds=123, expected_last_sequence=124),
        processor=processor,
    )
    processor.trip.add_observations(
        observation(i + 1, sec)
        for i, sec in enumerate(range(0, 123))
    )

    assert lifecycle.ready_for_sealing(processor) is False
    assert lifecycle.seal_if_ready(
        processor,
        FakeModel(),
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    ) is None


def test_terminal_tail_extends_last_mode_to_exact_trip_end():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    lifecycle = TripLifecycleState()
    model = FakeModel()

    processor.trip.add_observations(
        observation(i + 1, sec)
        for i, sec in enumerate(range(0, 724))
    )
    lifecycle.register_trip_end(
        trip_end(ended_seconds=723, expected_last_sequence=724),
        processor=processor,
    )

    sealed = lifecycle.seal_if_ready(
        processor,
        model,
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )

    assert sealed is not None
    assert processor.trip.last_prediction_end == BASE + timedelta(seconds=720)
    assert sealed.segments[-1].mode == "bus"
    assert sealed.segments[-1].end_time == BASE + timedelta(seconds=723)


def test_short_trip_returns_terminal_insufficient_data_result():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    lifecycle = TripLifecycleState()
    processor.trip.add_observations(
        observation(i + 1, sec)
        for i, sec in enumerate(range(0, 61))
    )
    lifecycle.register_trip_end(
        trip_end(ended_seconds=60, expected_last_sequence=61),
        processor=processor,
    )

    sealed = lifecycle.seal_if_ready(
        processor,
        FakeModel(),
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )

    assert sealed is not None
    assert sealed.status == "insufficient_data"
    assert sealed.reason == "trip_shorter_than_model_window"
    assert sealed.segments == ()


def test_no_complete_prediction_returns_terminal_insufficient_data_result():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    lifecycle = TripLifecycleState()
    processor.trip.add_observations(
        [
            observation(1, 0),
            observation(2, 121),
        ]
    )
    lifecycle.register_trip_end(
        trip_end(ended_seconds=121, expected_last_sequence=2),
        processor=processor,
    )

    sealed = lifecycle.seal_if_ready(
        processor,
        FakeModel(),
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )

    assert sealed is not None
    assert sealed.status == "insufficient_data"
    assert sealed.reason == "no_complete_model_prediction"
    assert sealed.segments == ()


def test_generation_is_emitted_only_once():
    processor = ModeDetectionProcessor.for_trip("trip-1", BASE)
    lifecycle = TripLifecycleState()
    model = FakeModel()
    processor.trip.add_observations(
        observation(i + 1, sec)
        for i, sec in enumerate(range(0, 124))
    )
    event = trip_end(ended_seconds=123, expected_last_sequence=124)
    lifecycle.register_trip_end(event, processor=processor)

    first = lifecycle.seal_if_ready(
        processor,
        model,
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )
    second = lifecycle.seal_if_ready(
        processor,
        model,
        raw_point_count_for_window=raw_count,
        transit_resolver=transit_resolver,
    )

    assert first is not None
    assert second is None

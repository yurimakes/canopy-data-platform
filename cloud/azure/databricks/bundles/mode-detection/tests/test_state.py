from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mode_detection.contract import (
    ModeModelMetadata,
    ModePrediction,
    Observation,
)
from mode_detection.state import TripProcessingState


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
    def __init__(self, *, window_seconds=120, stride_seconds=10):
        self._metadata = ModeModelMetadata(
            model_name="fake",
            model_version="1",
            feature_version="test",
            window_seconds=window_seconds,
            prediction_stride_seconds=stride_seconds,
        )
        self.calls = []

    @property
    def metadata(self):
        return self._metadata

    def prediction_ready(self, observations, *, window_end):
        start = window_end - timedelta(seconds=self.metadata.window_seconds)
        points = [p for p in observations if start <= p.event_time <= window_end]
        return (
            len(points) >= 2
            and points[0].event_time <= start
            and points[-1].event_time >= window_end
        )

    def predict(self, observations, *, window_end, raw_point_count):
        self.calls.append((window_end, raw_point_count))
        return ModePrediction(
            predicted_mode="bus",
            confidence=0.8,
            probabilities={"bus": 0.8, "walk": 0.2},
            window_start=window_end - timedelta(seconds=self.metadata.window_seconds),
            window_end=window_end,
            metadata=self.metadata,
        )


def raw_count(_start, _end, points):
    return len(points)


def test_observations_are_idempotent_by_sequence():
    state = TripProcessingState("trip-1", BASE)
    point = observation(1, 0)
    state.add_observations([point, point])
    assert state.observations == (point,)


def test_due_predictions_are_drained_in_order():
    state = TripProcessingState("trip-1", BASE)
    model = FakeModel()
    state.add_observations(observation(i + 1, sec) for i, sec in enumerate(range(0, 141)))

    predictions = state.drain_due_predictions(
        model,
        raw_point_count_for_window=raw_count,
    )

    assert [p.window_end for p in predictions] == [
        BASE + timedelta(seconds=120),
        BASE + timedelta(seconds=130),
        BASE + timedelta(seconds=140),
    ]
    assert state.last_prediction_end == BASE + timedelta(seconds=140)


def test_state_prunes_only_data_irrelevant_to_next_window():
    state = TripProcessingState("trip-1", BASE)
    model = FakeModel()
    state.add_observations(observation(i + 1, sec) for i, sec in enumerate(range(0, 141)))
    state.drain_due_predictions(model, raw_point_count_for_window=raw_count)

    # After the 140s prediction, the next 150s window starts at 30s.
    assert state.observations[0].event_time == BASE + timedelta(seconds=30)
    assert state.observations[-1].event_time == BASE + timedelta(seconds=140)


def test_future_batch_can_continue_from_last_prediction():
    state = TripProcessingState("trip-1", BASE)
    model = FakeModel()

    state.add_observations(observation(i + 1, sec) for i, sec in enumerate(range(0, 141)))
    state.drain_due_predictions(model, raw_point_count_for_window=raw_count)

    state.add_observations(
        observation(142 + i, sec)
        for i, sec in enumerate(range(141, 151))
    )
    predictions = state.drain_due_predictions(
        model,
        raw_point_count_for_window=raw_count,
    )

    assert [p.window_end for p in predictions] == [
        BASE + timedelta(seconds=150)
    ]


def test_not_ready_due_window_advances_scheduler_without_prediction():
    state = TripProcessingState("trip-1", BASE)
    model = FakeModel()

    # Latest data reaches 130s, but there is no observation exactly spanning
    # the first complete 0-120s window.
    state.add_observations([
        observation(1, 1),
        observation(2, 120),
        observation(3, 130),
    ])

    predictions = state.drain_due_predictions(
        model,
        raw_point_count_for_window=raw_count,
    )

    assert predictions == []
    assert state.last_prediction_end == BASE + timedelta(seconds=130)


def test_raw_point_count_policy_is_external_to_state():
    state = TripProcessingState("trip-1", BASE)
    model = FakeModel()
    state.add_observations([
        observation(1, 0),
        observation(2, 60),
        observation(3, 120),
    ])

    predictions = state.drain_due_predictions(
        model,
        raw_point_count_for_window=lambda _start, _end, _points: 99,
    )

    assert len(predictions) == 1
    assert model.calls == [(BASE + timedelta(seconds=120), 99)]

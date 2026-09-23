"""Pure per-trip observation and prediction scheduling state.

This module intentionally contains no Spark APIs. A later transformWithState
adapter can serialize this state while the core behavior remains unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .contract import ModeDetectingModel, ModePrediction, Observation
from .windowing import scheduled_prediction_ends


RawPointCountProvider = Callable[[datetime, datetime, Sequence[Observation]], int]


@dataclass
class TripProcessingState:
    trip_id: str
    trip_start: datetime
    observations_by_sequence: dict[int, Observation] = field(default_factory=dict)
    last_prediction_end: datetime | None = None

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(
            sorted(
                self.observations_by_sequence.values(),
                key=lambda point: (point.event_time, point.sequence),
            )
        )

    @property
    def latest_observation_time(self) -> datetime | None:
        points = self.observations
        return points[-1].event_time if points else None

    def add_observations(self, observations: Iterable[Observation]) -> None:
        """Add observations idempotently and reject sequence conflicts."""

        for point in observations:
            if point.event_time < self.trip_start:
                raise ValueError("observation precedes trip start")
            existing = self.observations_by_sequence.get(point.sequence)
            if existing is None:
                self.observations_by_sequence[point.sequence] = point
                continue
            if existing != point:
                raise ValueError(
                    f"conflicting observation for sequence {point.sequence}"
                )

    def due_prediction_ends(self, model: ModeDetectingModel) -> list[datetime]:
        latest = self.latest_observation_time
        if latest is None:
            return []
        return scheduled_prediction_ends(
            self.trip_start,
            latest,
            window_seconds=model.metadata.window_seconds,
            stride_seconds=model.metadata.prediction_stride_seconds,
            last_prediction_end=self.last_prediction_end,
        )

    def drain_due_predictions(
        self,
        model: ModeDetectingModel,
        *,
        raw_point_count_for_window: RawPointCountProvider,
    ) -> list[ModePrediction]:
        """Emit every ready stride-aligned prediction in chronological order.

        A due window that is not yet model-ready is not skipped. Draining stops
        there so prediction ordering remains deterministic if observations
        arrive out of order.
        """

        emitted: list[ModePrediction] = []
        for window_end in self.due_prediction_ends(model):
            points = self.observations
            if not model.prediction_ready(points, window_end=window_end):
                break

            window_start = window_end - timedelta(
                seconds=model.metadata.window_seconds
            )
            window_points = tuple(
                point
                for point in points
                if window_start <= point.event_time <= window_end
            )
            raw_point_count = raw_point_count_for_window(
                window_start,
                window_end,
                window_points,
            )
            prediction = model.predict(
                points,
                window_end=window_end,
                raw_point_count=raw_point_count,
            )
            emitted.append(prediction)
            self.last_prediction_end = window_end
            self._prune(model)

        return emitted

    def _prune(self, model: ModeDetectingModel) -> None:
        """Retain only observations that can affect the next prediction window."""

        if self.last_prediction_end is None:
            return
        next_window_end = self.last_prediction_end + timedelta(
            seconds=model.metadata.prediction_stride_seconds
        )
        cutoff = next_window_end - timedelta(
            seconds=model.metadata.window_seconds
        )
        self.observations_by_sequence = {
            sequence: point
            for sequence, point in self.observations_by_sequence.items()
            if point.event_time >= cutoff
        }

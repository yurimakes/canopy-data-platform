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
    max_contiguous_sequence: int = 0
    pending_sequences: set[int] = field(default_factory=set)
    gps_gap_tolerance_seconds: int = 15
    last_contiguous_point: Observation | None = None
    outages: list[tuple[datetime, datetime]] = field(default_factory=list)

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
        """Add observations idempotently, reject conflicts, and track completeness."""

        for point in observations:
            if point.event_time < self.trip_start:
                raise ValueError("observation precedes trip start")
            if point.sequence < 1:
                raise ValueError("observation sequence must be positive")

            existing = self.observations_by_sequence.get(point.sequence)
            if existing is not None:
                if existing != point:
                    raise ValueError(
                        f"conflicting observation for sequence {point.sequence}"
                    )
                continue

            # A sequence may already have been pruned after contributing to the
            # contiguous prefix. Replays of those rows are harmless.
            if point.sequence <= self.max_contiguous_sequence:
                continue

            self.observations_by_sequence[point.sequence] = point
            self.pending_sequences.add(point.sequence)
            self._advance_contiguous_sequence()

    def _advance_contiguous_sequence(self) -> None:
        next_sequence = self.max_contiguous_sequence + 1
        while next_sequence in self.pending_sequences:
            point = self.observations_by_sequence[next_sequence]
            if self.last_contiguous_point is not None:
                elapsed = (point.event_time - self.last_contiguous_point.event_time).total_seconds()
                if elapsed < 0:
                    raise ValueError("GPS event_time moves backwards across contiguous sequence")
                if elapsed > self.gps_gap_tolerance_seconds:
                    self.outages.append((self.last_contiguous_point.event_time, point.event_time))
            self.last_contiguous_point = point
            self.pending_sequences.remove(next_sequence)
            self.max_contiguous_sequence = next_sequence
            next_sequence += 1

    def has_complete_sequence_through(self, expected_last_sequence: int) -> bool:
        if expected_last_sequence < 1:
            raise ValueError("expected_last_sequence must be positive")
        return self.max_contiguous_sequence >= expected_last_sequence

    def due_prediction_ends(
        self,
        model: ModeDetectingModel,
        *,
        through: datetime | None = None,
    ) -> list[datetime]:
        # Future rows may arrive before earlier sequences. Only seal predictions
        # through the contiguous event-time prefix to avoid retroactive changes.
        latest = self.last_contiguous_point.event_time if self.last_contiguous_point else None
        if latest is None:
            return []
        horizon = min(latest, through) if through is not None else latest
        return scheduled_prediction_ends(
            self.trip_start,
            horizon,
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
        emitted: list[ModePrediction] = []
        for window_end in self.due_prediction_ends(model):
            points = self.supported_points(window_end, model.metadata.window_seconds)
            if points is None or not model.prediction_ready(points, window_end=window_end):
                self.last_prediction_end = window_end
                self._prune(model)
                continue

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

    def supported_points(self, window_end: datetime, window_seconds: int) -> tuple[Observation, ...] | None:
        """Select a continuous, recent inference window without changing model features."""
        preceding_outages = [gap for gap in self.outages if gap[0] < window_end]
        recovery = preceding_outages[-1][1] if preceding_outages else None
        if recovery is not None and (window_end - recovery).total_seconds() < window_seconds - self.gps_gap_tolerance_seconds:
            return None
        start = window_end - timedelta(seconds=window_seconds)
        points = tuple(p for p in self.observations if recovery is None or p.event_time >= recovery)
        selected = tuple(p for p in points if start <= p.event_time <= window_end)
        if not selected or (window_end - selected[-1].event_time).total_seconds() > self.gps_gap_tolerance_seconds:
            return None
        return points

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

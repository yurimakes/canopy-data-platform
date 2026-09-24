"""Glue for model inference, transit correction, and incremental segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .contract import ModeDetectingModel
from .distance import DistanceState
from .segmentation import SegmentState
from .state import RawPointCountProvider, TripProcessingState
from .transit import (
    TransitAdjustedPrediction,
    TransitContextState,
    TransitResolver,
)


@dataclass
class ModeDetectionProcessor:
    trip: TripProcessingState
    transit: TransitContextState
    segments: SegmentState
    distances: DistanceState
    skipped_prediction_windows: int = 0

    @classmethod
    def for_trip(cls, trip_id, trip_start):
        return cls(
            trip=TripProcessingState(trip_id=trip_id, trip_start=trip_start),
            transit=TransitContextState(),
            segments=SegmentState(trip_start=trip_start),
            distances=DistanceState(),
        )

    def drain_due_mode_updates(
        self,
        model: ModeDetectingModel,
        *,
        raw_point_count_for_window: RawPointCountProvider,
        transit_resolver: TransitResolver,
        through=None,
    ) -> list[TransitAdjustedPrediction]:
        """Drain scheduled predictions through transit correction into segments."""

        emitted: list[TransitAdjustedPrediction] = []

        for window_end in self.trip.due_prediction_ends(model, through=through):
            preceding_outages = [gap for gap in self.trip.outages if gap[0] < window_end]
            if preceding_outages:
                gap_start, recovered_at = preceding_outages[-1]
                if self.segments.current is None and self.segments.resume_start_time != recovered_at:
                    self.segments.mark_gap(gap_start, resume_at=recovered_at)
                elif self.segments.current is not None and self.segments.current.end_time <= gap_start and not self.segments.resume_after_gap:
                    self.segments.mark_gap(gap_start, resume_at=recovered_at)
            supported = self.trip.supported_points(window_end, model.metadata.window_seconds)
            if supported is None:
                if not self.segments.resume_after_gap:
                    self.segments.mark_gap(window_end)
                self.trip.last_prediction_end = window_end
                self.trip._prune(model)
                self.skipped_prediction_windows += 1
                continue
            points = supported
            if not model.prediction_ready(points, window_end=window_end):
                if not self.segments.resume_after_gap:
                    self.segments.mark_gap(window_end)
                self.trip.last_prediction_end = window_end
                self.trip._prune(model)
                self.skipped_prediction_windows += 1
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
            try:
                raw_prediction = model.predict(
                    points,
                    window_end=window_end,
                    raw_point_count=raw_point_count,
                )
            except ValueError:
                if not self.segments.resume_after_gap:
                    self.segments.mark_gap(window_end)
                self.trip.last_prediction_end = window_end
                self.trip._prune(model)
                self.skipped_prediction_windows += 1
                continue
            adjusted = self.transit.apply(
                raw_prediction,
                window_points,
                resolver=transit_resolver,
            )
            self.segments.apply(adjusted)
            emitted.append(adjusted)

            self.trip.last_prediction_end = window_end
            self.trip._prune(model)

        return emitted

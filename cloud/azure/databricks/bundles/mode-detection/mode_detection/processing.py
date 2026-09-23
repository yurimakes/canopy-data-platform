"""Glue for model inference, transit correction, and incremental segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .contract import ModeDetectingModel
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

    @classmethod
    def for_trip(cls, trip_id, trip_start):
        return cls(
            trip=TripProcessingState(trip_id=trip_id, trip_start=trip_start),
            transit=TransitContextState(),
            segments=SegmentState(trip_start=trip_start),
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
            points = self.trip.observations
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
            raw_prediction = model.predict(
                points,
                window_end=window_end,
                raw_point_count=raw_point_count,
            )
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

"""Trip-end lifecycle and segment sealing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .contract import ModeDetectingModel
from .processing import ModeDetectionProcessor
from .segmentation import ModeSegment
from .state import RawPointCountProvider
from .transit import TransitResolver


@dataclass(frozen=True)
class TripEnded:
    event_id: str
    trip_id: str
    user_id: str
    campaign_id: str
    started_at: datetime
    ended_at: datetime
    expected_last_sequence: int
    occurred_at: datetime
    processing_generation: int
    result_owner: str


@dataclass(frozen=True)
class SealedModeDetection:
    trip_end: TripEnded
    segments: tuple[ModeSegment, ...]
    status: str = "complete"
    reason: str | None = None


@dataclass
class TripLifecycleState:
    trip_end: TripEnded | None = None
    emitted_generations: set[int] = field(default_factory=set)

    def register_trip_end(self, event: TripEnded, *, processor: ModeDetectionProcessor) -> None:
        if event.trip_id != processor.trip.trip_id:
            raise ValueError("trip_end trip_id does not match processor state")
        if event.ended_at < event.started_at:
            raise ValueError("trip_end ended_at precedes started_at")
        if event.ended_at < processor.trip.trip_start:
            raise ValueError("trip_end ended_at precedes first GPS observation")
        if event.expected_last_sequence < 1:
            raise ValueError("expected_last_sequence must be positive")

        if self.trip_end is None:
            self.trip_end = event
            return
        if self.trip_end != event:
            raise ValueError("conflicting trip_end event")

    def ready_for_sealing(self, processor: ModeDetectionProcessor) -> bool:
        event = self.trip_end
        if event is None:
            return False
        return processor.trip.has_complete_sequence_through(
            event.expected_last_sequence
        )

    def seal_if_ready(
        self,
        processor: ModeDetectionProcessor,
        model: ModeDetectingModel,
        *,
        raw_point_count_for_window: RawPointCountProvider,
        transit_resolver: TransitResolver,
    ) -> SealedModeDetection | None:
        event = self.trip_end
        if event is None or not self.ready_for_sealing(processor):
            return None
        if event.processing_generation in self.emitted_generations:
            return None

        if (event.ended_at - event.started_at).total_seconds() < model.metadata.window_seconds:
            self.emitted_generations.add(event.processing_generation)
            return SealedModeDetection(
                event,
                (),
                status="insufficient_data",
                reason="trip_shorter_than_model_window",
            )

        processor.drain_due_mode_updates(
            model,
            raw_point_count_for_window=raw_point_count_for_window,
            transit_resolver=transit_resolver,
            through=event.ended_at,
        )

        if not processor.segments.segments:
            self.emitted_generations.add(event.processing_generation)
            return SealedModeDetection(
                event,
                (),
                status="insufficient_data",
                reason="no_complete_model_prediction",
            )

        segments = processor.segments.seal(
            event.ended_at,
            stride_seconds=model.metadata.prediction_stride_seconds,
        )
        self.emitted_generations.add(event.processing_generation)
        status = (
            "completed_partial"
            if processor.skipped_prediction_windows > 0
            else "ready"
        )
        reason = (
            "prediction_gaps"
            if processor.skipped_prediction_windows > 0
            else None
        )
        return SealedModeDetection(event, segments, status=status, reason=reason)

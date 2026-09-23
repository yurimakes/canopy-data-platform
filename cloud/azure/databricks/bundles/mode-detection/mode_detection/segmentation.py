"""Incremental segmentation over transit-adjusted mode decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .transit import TransitAdjustedPrediction


@dataclass(frozen=True)
class ModeSegment:
    mode: str
    start_time: datetime
    end_time: datetime
    confidence: float
    prediction_count: int


@dataclass
class SegmentState:
    """Build contiguous mode segments without smoothing or retroactive relabeling."""

    trip_start: datetime
    completed: list[ModeSegment] = field(default_factory=list)
    current: ModeSegment | None = None

    def apply(self, prediction: TransitAdjustedPrediction) -> None:
        decision_time = prediction.raw_prediction.window_end
        mode = prediction.final_mode
        confidence = prediction.confidence

        if decision_time < self.trip_start:
            raise ValueError("prediction precedes trip start")

        if self.current is None:
            # First complete 120-second prediction labels the initial trip history.
            self.current = ModeSegment(
                mode=mode,
                start_time=self.trip_start,
                end_time=decision_time,
                confidence=confidence,
                prediction_count=1,
            )
            return

        if decision_time <= self.current.end_time:
            raise ValueError("predictions must be applied in strictly increasing time order")

        if self.current.mode == mode:
            self.current = ModeSegment(
                mode=self.current.mode,
                start_time=self.current.start_time,
                end_time=decision_time,
                confidence=min(self.current.confidence, confidence),
                prediction_count=self.current.prediction_count + 1,
            )
            return

        self.completed.append(
            ModeSegment(
                mode=self.current.mode,
                start_time=self.current.start_time,
                end_time=decision_time,
                confidence=self.current.confidence,
                prediction_count=self.current.prediction_count,
            )
        )
        self.current = ModeSegment(
            mode=mode,
            start_time=decision_time,
            end_time=decision_time,
            confidence=confidence,
            prediction_count=1,
        )

    @property
    def segments(self) -> tuple[ModeSegment, ...]:
        if self.current is None:
            return tuple(self.completed)
        return (*self.completed, self.current)

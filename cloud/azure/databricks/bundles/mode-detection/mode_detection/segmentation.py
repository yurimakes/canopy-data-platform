"""Incremental segmentation over transit-adjusted mode decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .transit import TransitAdjustedPrediction
from .windowing import terminal_segment_end


@dataclass(frozen=True)
class ModeSegment:
    mode: str
    start_time: datetime
    end_time: datetime
    confidence: float
    prediction_count: int


@dataclass
class SegmentState:
    """Build mode segments while preserving explicit inference gaps."""

    trip_start: datetime
    completed: list[ModeSegment] = field(default_factory=list)
    current: ModeSegment | None = None
    sealed: bool = False
    resume_after_gap: bool = False
    resume_start_time: datetime | None = None

    def apply(self, prediction: TransitAdjustedPrediction) -> None:
        if self.sealed:
            raise ValueError("cannot apply prediction after segments are sealed")

        decision_time = prediction.raw_prediction.window_end
        mode = prediction.final_mode
        confidence = prediction.confidence

        if decision_time < self.trip_start:
            raise ValueError("prediction precedes trip start")

        if self.current is None:
            start_time = (self.resume_start_time or decision_time) if self.resume_after_gap else self.trip_start
            self.current = ModeSegment(
                mode=mode,
                start_time=start_time,
                end_time=decision_time,
                confidence=confidence,
                prediction_count=1,
            )
            self.resume_after_gap = False
            self.resume_start_time = None
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

    def mark_gap(self, gap_start: datetime, *, resume_at: datetime | None = None) -> None:
        """Close inferred coverage at a missing prediction boundary."""
        if self.sealed:
            raise ValueError("cannot mark a gap after segments are sealed")
        if self.current is not None:
            self.completed.append(
                ModeSegment(
                    mode=self.current.mode,
                    start_time=self.current.start_time,
                    end_time=max(self.current.end_time, gap_start) if resume_at is not None else min(self.current.end_time, gap_start),
                    confidence=self.current.confidence,
                    prediction_count=self.current.prediction_count,
                )
            )
            self.current = None
        self.resume_after_gap = True
        self.resume_start_time = resume_at

    def seal(self, trip_end: datetime, *, stride_seconds: int) -> tuple[ModeSegment, ...]:
        if self.sealed:
            return self.segments
        if self.current is None:
            if self.completed:
                self.sealed = True
                return self.segments
            raise ValueError("cannot seal trip without a mode prediction")

        terminal_segment_end(
            last_prediction_end=self.current.end_time,
            trip_end=trip_end,
            stride_seconds=stride_seconds,
        )
        self.current = ModeSegment(
            mode=self.current.mode,
            start_time=self.current.start_time,
            end_time=trip_end,
            confidence=self.current.confidence,
            prediction_count=self.current.prediction_count,
        )
        self.sealed = True
        return self.segments

    @property
    def segments(self) -> tuple[ModeSegment, ...]:
        if self.current is None:
            return tuple(self.completed)
        return (*self.completed, self.current)

"""Bounded inference for a closed first-layer segment."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Protocol, Sequence

from .mock_detector import SegmentEvent
from .windowing import build_speed_windows


DEFAULT_CLASSES = ("bike", "bus", "car", "train", "walk")


class PyfuncModel(Protocol):
    def predict(self, model_input: Any) -> Any: ...


@dataclass(frozen=True)
class SegmentInferenceResult:
    trip_id: str
    user_id: str
    segment_id: str
    start_time: Any
    end_time: Any
    weak_mode: str
    weak_confidence: float
    detector_version: str
    status: str
    strong_mode: str | None
    strong_confidence: float | None
    probabilities: tuple[float, ...] | None
    window_count: int
    speed_point_count: int


def infer_closed_segment(
    segment: SegmentEvent,
    speeds_kmh: Sequence[float],
    model: PyfuncModel,
    *,
    classes: tuple[str, ...] = DEFAULT_CLASSES,
) -> SegmentInferenceResult:
    """Score all representative windows once and mean-aggregate probabilities.

    Insufficient history is returned as a retryable result rather than raising;
    it can occur when the segment record becomes visible before its final Silver
    GPS point. Invalid values and malformed model output remain hard failures.
    """
    if len(speeds_kmh) > segment.speed_point_count:
        raise ValueError("persisted history exceeds detector-declared speed_point_count")

    history_complete = len(speeds_kmh) == segment.speed_point_count
    windows = build_speed_windows(speeds_kmh)
    if not history_complete or not windows:
        return SegmentInferenceResult(
            trip_id=segment.trip_id,
            user_id=segment.user_id,
            segment_id=segment.segment_id,
            start_time=segment.start_time,
            end_time=segment.end_time,
            weak_mode=segment.weak_mode,
            weak_confidence=segment.weak_confidence,
            detector_version=segment.detector_version,
            status="insufficient_history",
            strong_mode=None,
            strong_confidence=None,
            probabilities=None,
            window_count=len(windows),
            speed_point_count=len(speeds_kmh),
        )

    # Import at the serving boundary so the framework-neutral streaming core
    # does not require pandas merely to calculate features or mock segments.
    import pandas as pd

    model_input = pd.DataFrame(
        {"speed_sequence": [list(window.speed_sequence) for window in windows]}
    )
    predictions = model.predict(model_input)
    rows = _probability_rows(predictions, expected_rows=len(windows), classes=classes)
    aggregate = tuple(
        sum(row[class_index] for row in rows) / len(rows)
        for class_index in range(len(classes))
    )
    best_index = max(range(len(classes)), key=aggregate.__getitem__)

    return SegmentInferenceResult(
        trip_id=segment.trip_id,
        user_id=segment.user_id,
        segment_id=segment.segment_id,
        start_time=segment.start_time,
        end_time=segment.end_time,
        weak_mode=segment.weak_mode,
        weak_confidence=segment.weak_confidence,
        detector_version=segment.detector_version,
        status="scored",
        strong_mode=classes[best_index],
        strong_confidence=aggregate[best_index],
        probabilities=aggregate,
        window_count=len(windows),
        speed_point_count=len(speeds_kmh),
    )


def _probability_rows(
    predictions: Any,
    *,
    expected_rows: int,
    classes: tuple[str, ...],
) -> tuple[tuple[float, ...], ...]:
    required = {"predicted_class", "confidence", "probabilities"}
    columns = set(getattr(predictions, "columns", ()))
    if not required.issubset(columns):
        raise ValueError(f"model output is missing columns: {sorted(required - columns)}")
    if len(predictions) != expected_rows:
        raise ValueError("model output row count does not match input window count")

    rows: list[tuple[float, ...]] = []
    for raw in predictions["probabilities"]:
        row = tuple(float(value) for value in raw)
        if len(row) != len(classes):
            raise ValueError("probability vector length does not match class order")
        if any(not math.isfinite(value) or value < 0.0 for value in row):
            raise ValueError("probabilities must be finite and non-negative")
        if not math.isclose(sum(row), 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError("each probability vector must sum to 1")
        rows.append(row)
    return tuple(rows)

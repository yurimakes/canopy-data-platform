"""Stable runtime contract between streaming state and mode-detection models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class Observation:
    sequence: int
    event_time: datetime
    lat: float
    lon: float
    accuracy_m: float | None
    altitude_m: float | None


@dataclass(frozen=True)
class ModeModelMetadata:
    model_name: str
    model_version: str
    feature_version: str
    window_seconds: int
    prediction_stride_seconds: int


@dataclass(frozen=True)
class ModePrediction:
    predicted_mode: str
    confidence: float
    probabilities: Mapping[str, float]
    window_start: datetime
    window_end: datetime
    metadata: ModeModelMetadata


class ModeDetectingModel(Protocol):
    """Model boundary used by the streaming trip processor."""

    @property
    def metadata(self) -> ModeModelMetadata: ...

    def prediction_ready(
        self,
        observations: Sequence[Observation],
        *,
        window_end: datetime,
    ) -> bool: ...

    def predict(
        self,
        observations: Sequence[Observation],
        *,
        window_end: datetime,
        raw_point_count: int,
    ) -> ModePrediction: ...

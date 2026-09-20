"""Pure incremental trip segmentation with bounded smoothing lookahead."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


EARTH_RADIUS_M = 6_371_008.8
MAX_SEQUENCE = 10_000_000
SEGMENTATION_VERSION = "time-segmentation-v1"


@dataclass(frozen=True)
class PredictionPoint:
    event_id: str
    user_id: str
    trip_id: str
    sequence: int
    event_time: datetime
    lat: float
    lon: float
    predicted_mode: str
    confidence: float | None
    model_name: str
    model_version: str | None
    predicted_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> tuple[Any, ...]:
        return tuple(self.as_dict().values())


@dataclass(frozen=True)
class TripEnd:
    event_id: str
    trip_id: str
    user_id: str
    expected_last_sequence: int
    processing_generation: int
    parsed_at: datetime
    result_owner: str

    def fingerprint(self) -> tuple[Any, ...]:
        return tuple(asdict(self).values())


@dataclass(frozen=True)
class SegmentRow:
    trip_id: str
    user_id: str
    processing_generation: int
    segment_index: int
    segment_id: str
    mode: str
    start_sequence: int
    end_sequence: int
    start_time: datetime
    end_time: datetime
    point_count: int
    distance_m: float
    confidence: float | None
    model_name: str
    model_version: str | None
    latest_prediction_at: datetime
    trip_end_parsed_at: datetime
    segmentation_version: str
    segmented_at: datetime


@dataclass(frozen=True)
class _ModePoint:
    point: PredictionPoint
    mode: str


@dataclass
class _SegmentAccumulator:
    user_id: str
    mode: str
    start_sequence: int
    end_sequence: int
    start_time: datetime
    end_time: datetime
    point_count: int
    distance_m: float
    model_name: str
    model_version: str | None
    latest_prediction_at: datetime
    last_lat: float
    last_lon: float

    @classmethod
    def start(cls, value: _ModePoint) -> _SegmentAccumulator:
        point = value.point
        return cls(
            user_id=point.user_id,
            mode=value.mode,
            start_sequence=point.sequence,
            end_sequence=point.sequence,
            start_time=point.event_time,
            end_time=point.event_time,
            point_count=1,
            distance_m=0.0,
            model_name=point.model_name,
            model_version=point.model_version,
            latest_prediction_at=point.predicted_at,
            last_lat=point.lat,
            last_lon=point.lon,
        )

    def append(self, value: _ModePoint) -> None:
        point = value.point
        self.distance_m += _haversine_m(
            self.last_lat,
            self.last_lon,
            point.lat,
            point.lon,
        )
        self.end_sequence = point.sequence
        self.end_time = point.event_time
        self.point_count += 1
        self.model_name = min(self.model_name, point.model_name)
        if point.model_version is not None:
            self.model_version = (
                point.model_version
                if self.model_version is None
                else min(self.model_version, point.model_version)
            )
        self.latest_prediction_at = max(
            self.latest_prediction_at,
            point.predicted_at,
        )
        self.last_lat = point.lat
        self.last_lon = point.lon


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, value)))


def _gap_seconds(left: PredictionPoint, right: PredictionPoint) -> float:
    return (right.event_time - left.event_time).total_seconds()


def _within_gap(
    left: PredictionPoint,
    right: PredictionPoint,
    max_gap_seconds: int,
) -> bool:
    return 0.0 <= _gap_seconds(left, right) <= max_gap_seconds


@dataclass
class TripSegmentationState:
    """Advance one trip without rescanning its point history at finalization."""

    trip_id: str
    max_gap_seconds: int
    _next_sequence: int = 1
    _pending: dict[int, PredictionPoint] = field(default_factory=dict)
    _fingerprints: dict[int, tuple[Any, ...]] = field(default_factory=dict)
    _raw_window: list[PredictionPoint] = field(default_factory=list)
    _repaired_window: list[_ModePoint] = field(default_factory=list)
    _completed_segments: list[_SegmentAccumulator] = field(default_factory=list)
    _current_segment: _SegmentAccumulator | None = None
    _trip_ends: dict[int, TripEnd] = field(default_factory=dict)
    _ready_generations: list[int] = field(default_factory=list)
    _emitted_generations: set[int] = field(default_factory=set)
    _sealed_at: int | None = None
    conflicted: bool = False

    def __post_init__(self) -> None:
        if not self.trip_id:
            raise ValueError("trip_id must not be empty")
        if self.max_gap_seconds < 0:
            raise ValueError("max_gap_seconds must be non-negative")

    def accept_prediction(self, point: PredictionPoint) -> None:
        if self.conflicted:
            return
        if point.trip_id != self.trip_id:
            raise ValueError("grouping key does not match prediction trip_id")
        if not 1 <= point.sequence <= MAX_SEQUENCE:
            self.conflicted = True
            return

        fingerprint = point.fingerprint()
        existing = self._fingerprints.get(point.sequence)
        if existing is not None:
            if existing != fingerprint:
                self.conflicted = True
            return

        if self._sealed_at is not None:
            self.conflicted = True
            return

        self._fingerprints[point.sequence] = fingerprint
        self._pending[point.sequence] = point
        while self._next_sequence in self._pending:
            current = self._pending.pop(self._next_sequence)
            self._append_raw(current)
            self._next_sequence += 1
        self._evaluate_readiness()

    def accept_trip_end(self, event: TripEnd) -> None:
        if self.conflicted:
            return
        if event.trip_id != self.trip_id:
            raise ValueError("grouping key does not match trip-end trip_id")
        if event.result_owner != "databricks":
            return
        if event.processing_generation < 1 or not 1 <= event.expected_last_sequence <= MAX_SEQUENCE:
            self.conflicted = True
            return

        existing = self._trip_ends.get(event.processing_generation)
        if existing is not None:
            if existing.fingerprint() != event.fingerprint():
                self.conflicted = True
            return

        self._trip_ends[event.processing_generation] = event
        self._evaluate_readiness()

    def drain_outputs(self, segmented_at: datetime) -> list[SegmentRow]:
        if self.conflicted:
            self._ready_generations.clear()
            return []

        rows: list[SegmentRow] = []
        while self._ready_generations:
            generation = self._ready_generations.pop(0)
            if generation in self._emitted_generations:
                continue
            event = self._trip_ends[generation]
            segments = [*self._completed_segments]
            if self._current_segment is not None:
                segments.append(self._current_segment)
            for index, segment in enumerate(segments, start=1):
                rows.append(
                    SegmentRow(
                        trip_id=self.trip_id,
                        user_id=segment.user_id,
                        processing_generation=generation,
                        segment_index=index,
                        segment_id=(
                            f"{self.trip_id}:g{generation}:segment:{index}"
                        ),
                        mode=segment.mode,
                        start_sequence=segment.start_sequence,
                        end_sequence=segment.end_sequence,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        point_count=segment.point_count,
                        distance_m=segment.distance_m,
                        confidence=None,
                        model_name=segment.model_name,
                        model_version=segment.model_version,
                        latest_prediction_at=segment.latest_prediction_at,
                        trip_end_parsed_at=event.parsed_at,
                        segmentation_version=SEGMENTATION_VERSION,
                        segmented_at=segmented_at,
                    )
                )
            self._emitted_generations.add(generation)
        return rows

    def _evaluate_readiness(self) -> None:
        if self.conflicted:
            return
        contiguous_last = self._next_sequence - 1
        for generation in sorted(self._trip_ends):
            if generation in self._emitted_generations or generation in self._ready_generations:
                continue
            event = self._trip_ends[generation]
            expected = event.expected_last_sequence
            if self._sealed_at is not None:
                if expected != self._sealed_at:
                    self.conflicted = True
                    return
                self._ready_generations.append(generation)
                continue
            if contiguous_last > expected:
                self.conflicted = True
                return
            if contiguous_last < expected:
                continue
            if self._pending:
                self.conflicted = True
                return
            self._flush_smoothing_tail()
            self._sealed_at = expected
            self._ready_generations.append(generation)

    def _append_raw(self, point: PredictionPoint) -> None:
        self._raw_window.append(point)
        if len(self._raw_window) >= 2:
            current = self._raw_window[-2]
            repaired_mode = current.predicted_mode
            if len(self._raw_window) >= 4:
                lag2, lag1, current, lead1 = self._raw_window[-4:]
                if (
                    lag2.predicted_mode == current.predicted_mode
                    and lag1.predicted_mode == lead1.predicted_mode
                    and lag1.predicted_mode != current.predicted_mode
                    and _within_gap(lag2, lag1, self.max_gap_seconds)
                    and _within_gap(lag1, current, self.max_gap_seconds)
                    and _within_gap(current, lead1, self.max_gap_seconds)
                ):
                    repaired_mode = lag1.predicted_mode
            self._append_repaired(_ModePoint(current, repaired_mode))
        self._raw_window = self._raw_window[-3:]

    def _append_repaired(self, value: _ModePoint) -> None:
        self._repaired_window.append(value)
        if len(self._repaired_window) >= 2:
            current = self._repaired_window[-2]
            stabilized_mode = current.mode
            if len(self._repaired_window) >= 3:
                lag1, current, lead1 = self._repaired_window[-3:]
                if (
                    lag1.mode == lead1.mode
                    and current.mode != lag1.mode
                    and _within_gap(lag1.point, current.point, self.max_gap_seconds)
                    and _within_gap(current.point, lead1.point, self.max_gap_seconds)
                ):
                    stabilized_mode = lag1.mode
            self._consume_stabilized(_ModePoint(current.point, stabilized_mode))
        self._repaired_window = self._repaired_window[-2:]

    def _flush_smoothing_tail(self) -> None:
        if self._raw_window:
            last = self._raw_window[-1]
            self._append_repaired(_ModePoint(last, last.predicted_mode))
            self._raw_window.clear()
        if self._repaired_window:
            self._consume_stabilized(self._repaired_window[-1])
            self._repaired_window.clear()

    def _consume_stabilized(self, value: _ModePoint) -> None:
        if self._current_segment is None:
            self._current_segment = _SegmentAccumulator.start(value)
        elif self._current_segment.mode == value.mode:
            self._current_segment.append(value)
        else:
            self._completed_segments.append(self._current_segment)
            self._current_segment = _SegmentAccumulator.start(value)

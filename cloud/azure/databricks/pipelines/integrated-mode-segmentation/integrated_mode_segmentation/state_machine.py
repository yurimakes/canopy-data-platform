"""Pure incremental trip segmentation with bounded smoothing lookahead."""

from __future__ import annotations

import math
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
        values = asdict(self)
        values["event_time"] = _utc_naive(self.event_time)
        values["predicted_at"] = _utc_naive(self.predicted_at)
        return values

    def fingerprint(self) -> str:
        return _fingerprint(self.as_dict())


@dataclass(frozen=True)
class TripEnd:
    event_id: str
    trip_id: str
    user_id: str
    expected_last_sequence: int
    processing_generation: int
    parsed_at: datetime
    result_owner: str

    def fingerprint(self) -> str:
        values = asdict(self)
        # parsed_at is ingestion metadata, not part of the logical lifecycle event.
        # Replays of the same event can legitimately receive a new parsed_at value.
        values.pop("parsed_at", None)
        return _fingerprint(values)


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
            start_time=_utc_naive(point.event_time),
            end_time=_utc_naive(point.event_time),
            point_count=1,
            distance_m=0.0,
            model_name=point.model_name,
            model_version=point.model_version,
            latest_prediction_at=_utc_naive(point.predicted_at),
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
        self.end_time = _utc_naive(point.event_time)
        self.point_count += 1
        self.model_name = min(self.model_name, point.model_name)
        if point.model_version is not None:
            self.model_version = (
                point.model_version
                if self.model_version is None
                else min(self.model_version, point.model_version)
            )
        self.latest_prediction_at = max(
            _utc_naive(self.latest_prediction_at),
            _utc_naive(point.predicted_at),
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


def _fingerprint(values: dict[str, Any]) -> str:
    encoded = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "asDict"):
        return value.asDict(recursive=True)
    raise TypeError(f"state value must be mapping-like, got {type(value).__name__}")


def _utc_naive(value: datetime) -> datetime:
    """Normalize Spark/Pandas timestamps to naive UTC for stable state comparisons."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _gap_seconds(left: PredictionPoint, right: PredictionPoint) -> float:
    def epoch_second(value: datetime) -> int:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return math.floor(normalized.timestamp())

    # The batch reference uses Spark unix_timestamp(), which compares whole
    # epoch seconds rather than exact Python timedeltas.
    return float(epoch_second(right.event_time) - epoch_second(left.event_time))


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
    _fingerprints: dict[int, str] = field(default_factory=dict)
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

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "trip_id": self.trip_id,
            "max_gap_seconds": self.max_gap_seconds,
            "next_sequence": self._next_sequence,
            "pending": [point.as_dict() for _, point in sorted(self._pending.items())],
            "fingerprints": dict(self._fingerprints),
            "raw_window": [point.as_dict() for point in self._raw_window],
            "repaired_window": [
                {"point": value.point.as_dict(), "mode": value.mode}
                for value in self._repaired_window
            ],
            "completed_segments": [asdict(value) for value in self._completed_segments],
            "current_segment": (
                None if self._current_segment is None else asdict(self._current_segment)
            ),
            "trip_ends": [asdict(value) for _, value in sorted(self._trip_ends.items())],
            "ready_generations": list(self._ready_generations),
            "emitted_generations": sorted(self._emitted_generations),
            "sealed_at": self._sealed_at,
            "conflicted": self.conflicted,
        }

    @classmethod
    def from_state_dict(cls, value: Any) -> TripSegmentationState:
        data = _mapping(value)
        state = cls(
            trip_id=str(data["trip_id"]),
            max_gap_seconds=int(data["max_gap_seconds"]),
        )
        state._next_sequence = int(data["next_sequence"])
        pending = [PredictionPoint(**_mapping(item)) for item in data.get("pending", [])]
        state._pending = {point.sequence: point for point in pending}
        state._fingerprints = {
            int(sequence): str(digest)
            for sequence, digest in dict(data.get("fingerprints", {})).items()
        }
        state._raw_window = [
            PredictionPoint(**_mapping(item)) for item in data.get("raw_window", [])
        ]
        state._repaired_window = [
            _ModePoint(
                PredictionPoint(**_mapping(_mapping(item)["point"])),
                str(_mapping(item)["mode"]),
            )
            for item in data.get("repaired_window", [])
        ]
        state._completed_segments = [
            _SegmentAccumulator(**_mapping(item))
            for item in data.get("completed_segments", [])
        ]
        current = data.get("current_segment")
        state._current_segment = (
            None if current is None else _SegmentAccumulator(**_mapping(current))
        )
        ends = [TripEnd(**_mapping(item)) for item in data.get("trip_ends", [])]
        state._trip_ends = {item.processing_generation: item for item in ends}
        state._ready_generations = [int(item) for item in data.get("ready_generations", [])]
        state._emitted_generations = {
            int(item) for item in data.get("emitted_generations", [])
        }
        sealed_at = data.get("sealed_at")
        state._sealed_at = None if sealed_at is None else int(sealed_at)
        state.conflicted = bool(data.get("conflicted", False))
        return state

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
        if event.processing_generation < 1 or not 1 <= event.expected_last_sequence <= MAX_SEQUENCE:
            self.conflicted = True
            return

        existing = self._trip_ends.get(event.processing_generation)
        if existing is not None:
            if existing.fingerprint() != event.fingerprint():
                self.conflicted = True
            return

        self._trip_ends[event.processing_generation] = event
        if event.result_owner != "databricks":
            return
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
            if event.result_owner != "databricks":
                continue
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

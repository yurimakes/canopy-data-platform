"""Replaceable mock implementation of the first-layer detector contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import random
from typing import Any, Mapping


DEFAULT_MODES = ("bike", "bus", "car", "train", "walk")


@dataclass(frozen=True)
class MockDetectorConfig:
    min_speed_points: int = 250
    max_speed_points: int = 300
    modes: tuple[str, ...] = DEFAULT_MODES
    seed: int = 316
    detector_version: str = "mock-random-v2"

    def __post_init__(self) -> None:
        if self.min_speed_points < 250:
            raise ValueError("mock segments must contain at least 250 speed points")
        if self.max_speed_points < self.min_speed_points:
            raise ValueError("max_speed_points must be >= min_speed_points")
        if not self.modes:
            raise ValueError("at least one mock mode is required")


@dataclass(frozen=True)
class DetectorPoint:
    trip_id: str
    user_id: str
    event_time: datetime
    speed_min_60s: float


@dataclass(frozen=True)
class SegmentEvent:
    trip_id: str
    user_id: str
    segment_id: str
    start_time: datetime
    end_time: datetime
    speed_point_count: int
    weak_mode: str
    weak_confidence: float
    status: str
    detector_version: str


@dataclass
class _TripState:
    rng: random.Random
    segment_number: int
    target_points: int
    point_count: int = 0
    start_time: datetime | None = None


class MockFirstLayerDetector:
    """Emit reproducible random weak predictions for 250–300-point segments.

    ``speed_min_60s`` is intentionally accepted through ``DetectorPoint`` but
    is not used. It reserves the feature contract for the future real model.
    """

    def __init__(self, config: MockDetectorConfig | None = None) -> None:
        self.config = config or MockDetectorConfig()
        self._trips: dict[str, _TripState] = {}

    def process(self, point: DetectorPoint) -> SegmentEvent | None:
        state = self._trips.get(point.trip_id)
        if state is None:
            rng = random.Random(self._trip_seed(point.trip_id))
            state = _TripState(
                rng=rng,
                segment_number=1,
                target_points=rng.randint(
                    self.config.min_speed_points, self.config.max_speed_points
                ),
            )
            self._trips[point.trip_id] = state

        if state.start_time is None:
            state.start_time = point.event_time
        state.point_count += 1

        if state.point_count < state.target_points:
            return None

        event = SegmentEvent(
            trip_id=point.trip_id,
            user_id=point.user_id,
            segment_id=f"{point.trip_id}:mock:{state.segment_number:04d}",
            start_time=state.start_time,
            end_time=point.event_time,
            speed_point_count=state.point_count,
            weak_mode=state.rng.choice(self.config.modes),
            weak_confidence=round(state.rng.uniform(0.5, 0.95), 6),
            status="closed",
            detector_version=self.config.detector_version,
        )

        state.segment_number += 1
        state.target_points = state.rng.randint(
            self.config.min_speed_points, self.config.max_speed_points
        )
        state.point_count = 0
        state.start_time = None
        return event

    def pending_speed_points(self, trip_id: str) -> int:
        state = self._trips.get(trip_id)
        return 0 if state is None else state.point_count

    def clear_trip(self, trip_id: str) -> int:
        """Drop, rather than emit, an ineligible final partial segment."""
        state = self._trips.pop(trip_id, None)
        return 0 if state is None else state.point_count

    def snapshot_trip(self, trip_id: str) -> dict[str, Any] | None:
        state = self._trips.get(trip_id)
        if state is None:
            return None
        return {
            "rng_state": state.rng.getstate(),
            "segment_number": state.segment_number,
            "target_points": state.target_points,
            "point_count": state.point_count,
            "start_time": None if state.start_time is None else state.start_time.isoformat(),
        }

    def restore_trip(self, trip_id: str, snapshot: Mapping[str, Any] | None) -> None:
        self._trips.pop(trip_id, None)
        if not snapshot:
            return
        target_points = int(snapshot["target_points"])
        point_count = int(snapshot["point_count"])
        if not self.config.min_speed_points <= target_points <= self.config.max_speed_points:
            raise ValueError(
                "persisted mock detector target is incompatible with the configured range"
            )
        if not 0 <= point_count < target_points:
            raise ValueError("persisted mock detector point count is invalid")
        rng = random.Random()
        rng.setstate(_nested_tuple(snapshot["rng_state"]))
        start_time = snapshot.get("start_time")
        self._trips[trip_id] = _TripState(
            rng=rng,
            segment_number=int(snapshot["segment_number"]),
            target_points=target_points,
            point_count=point_count,
            start_time=None if start_time is None else datetime.fromisoformat(str(start_time)),
        )

    def _trip_seed(self, trip_id: str) -> int:
        material = f"{self.config.seed}:{trip_id}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _nested_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_nested_tuple(item) for item in value)
    return value

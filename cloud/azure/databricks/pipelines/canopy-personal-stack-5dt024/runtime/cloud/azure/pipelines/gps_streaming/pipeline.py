"""Framework-neutral stateful core for Silver features and mock segments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .features import RollingSpeedMin
from .mock_detector import DetectorPoint, MockFirstLayerDetector, SegmentEvent


@dataclass(frozen=True)
class EnrichedSpeedPoint:
    trip_id: str
    user_id: str
    event_time: datetime
    derived_speed_kmh: float
    speed_min_60s: float


class MockFirstLayerPipeline:
    """Calculate persisted features, then invoke the replaceable detector."""

    def __init__(self, detector: MockFirstLayerDetector | None = None) -> None:
        self.features = RollingSpeedMin()
        self.detector = detector or MockFirstLayerDetector()

    def process(
        self,
        *,
        trip_id: str,
        user_id: str,
        event_time: datetime,
        derived_speed_kmh: float,
    ) -> tuple[EnrichedSpeedPoint, SegmentEvent | None]:
        speed_min_60s = self.features.update(
            trip_id=trip_id,
            event_time=event_time,
            speed_kmh=derived_speed_kmh,
        )
        enriched = EnrichedSpeedPoint(
            trip_id=trip_id,
            user_id=user_id,
            event_time=event_time,
            derived_speed_kmh=float(derived_speed_kmh),
            speed_min_60s=speed_min_60s,
        )
        segment = self.detector.process(
            DetectorPoint(
                trip_id=trip_id,
                user_id=user_id,
                event_time=event_time,
                speed_min_60s=speed_min_60s,
            )
        )
        return enriched, segment

    def clear_trip(self, trip_id: str) -> int:
        self.features.clear_trip(trip_id)
        return self.detector.clear_trip(trip_id)

    def snapshot_trip(self, trip_id: str) -> dict[str, Any]:
        return {
            "features": self.features.snapshot_trip(trip_id),
            "detector": self.detector.snapshot_trip(trip_id),
        }

    def restore_trip(self, trip_id: str, snapshot: Mapping[str, Any] | None) -> None:
        snapshot = snapshot or {}
        self.features.restore_trip(trip_id, snapshot.get("features"))
        self.detector.restore_trip(trip_id, snapshot.get("detector"))

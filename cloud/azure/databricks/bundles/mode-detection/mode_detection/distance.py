"""Compact per-trip path-distance state independent of model window pruning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from .contract import Observation
from .segmentation import ModeSegment

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class DistanceLeg:
    end_time: datetime
    distance_m: float


def haversine_m(left: Observation, right: Observation) -> float:
    lat1, lon1, lat2, lon2 = map(
        radians, (left.lat, left.lon, right.lat, right.lon)
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * asin(min(1.0, sqrt(h)))


@dataclass
class DistanceState:
    """Retain only one previous point, out-of-order pending points, and path legs."""

    last_point: Observation | None = None
    pending: dict[int, Observation] = field(default_factory=dict)
    legs: list[DistanceLeg] = field(default_factory=list)

    def add_observations(self, observations) -> None:
        for point in observations:
            if self.last_point is not None and point.sequence <= self.last_point.sequence:
                continue
            existing = self.pending.get(point.sequence)
            if existing is not None and existing != point:
                raise ValueError(f"conflicting distance observation sequence {point.sequence}")
            self.pending[point.sequence] = point

        if self.last_point is None:
            first = self.pending.pop(1, None)
            if first is None:
                return
            self.last_point = first

        while True:
            sequence = self.last_point.sequence + 1
            current = self.pending.pop(sequence, None)
            if current is None:
                break
            if current.event_time < self.last_point.event_time:
                raise ValueError("GPS event_time moves backwards across contiguous sequence")
            self.legs.append(
                DistanceLeg(
                    end_time=current.event_time,
                    distance_m=haversine_m(self.last_point, current),
                )
            )
            self.last_point = current

    def distances_for(self, segments: tuple[ModeSegment, ...]) -> tuple[float, ...]:
        if not segments:
            return ()
        totals = [0.0] * len(segments)
        for leg in self.legs:
            index = next(
                (
                    i
                    for i, segment in enumerate(segments)
                    if segment.start_time < leg.end_time <= segment.end_time
                ),
                None,
            )
            if index is not None:
                totals[index] += leg.distance_m
        return tuple(totals)

"""Reference-compatible point-count GPS trajectory feature engineering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .contracts import FEATURE_NAMES

EARTH_RADIUS_M = 6_371_000.0
STOP_THRESHOLD_KMH = 3.0


@dataclass(frozen=True)
class GpsPoint:
    event_id: str
    user_id: str
    trip_id: str
    sequence: int
    event_time: datetime
    lat: float
    lon: float


def _distance(left: GpsPoint, right: GpsPoint) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians, (left.lat, left.lon, right.lat, right.lon)
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return EARTH_RADIUS_M * 2.0 * math.asin(min(1.0, math.sqrt(a)))


def _bearing(left: GpsPoint, right: GpsPoint) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians, (left.lat, left.lon, right.lat, right.lon)
    )
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y))


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def extract_features(points: Sequence[GpsPoint]) -> list[dict[str, float]]:
    """Return one reference-compatible feature row for every ordered point."""
    if not points:
        return []
    speeds: list[float] = []
    accelerations: list[float] = []
    bearings: list[float] = []
    output: list[dict[str, float]] = []

    for index, point in enumerate(points):
        if index == 0:
            dt = 0.1
            distance = 0.0
            bearing = 0.0
        else:
            previous = points[index - 1]
            dt = max((point.event_time - previous.event_time).total_seconds(), 0.1)
            distance = _distance(previous, point)
            bearing = _bearing(previous, point)

        speed = distance / dt * 3.6
        acceleration = 0.0 if index == 0 else (speed - speeds[-1]) / dt
        previous_bearing = 0.0 if index == 0 else bearings[-1]
        bearing_difference = abs(bearing - previous_bearing)
        bearing_change = 360.0 - bearing_difference if bearing_difference > 180.0 else bearing_difference

        speeds.append(speed)
        accelerations.append(acceleration)
        bearings.append(bearing)

        speed_5 = speeds[-5:]
        speed_10 = speeds[-10:]
        speed_30 = speeds[-30:]
        speed_60 = speeds[-60:]
        speed_150 = speeds[-150:]
        accel_30 = accelerations[-30:]
        stopped_60 = [1.0 if value < STOP_THRESHOLD_KMH else 0.0 for value in speed_60]
        stopped_150 = [1.0 if value < STOP_THRESHOLD_KMH else 0.0 for value in speed_150]

        row = {
            "speed": speed,
            "acceleration": acceleration,
            "distance": distance,
            "bearing_change": bearing_change,
            "speed_mean_5": _mean(speed_5),
            "speed_std_5": _sample_std(speed_5),
            "speed_max_10": max(speed_10),
            "speed_mean_30": _mean(speed_30),
            "speed_std_30": _sample_std(speed_30),
            "speed_max_60": max(speed_60),
            "speed_mean_150": _mean(speed_150),
            "stop_count_60": math.fsum(stopped_60),
            "stop_count_150": math.fsum(stopped_150),
            "stoppage_ratio_60": _mean(stopped_60),
            "speed_q25_60": _quantile(speed_60, 0.25),
            "speed_q75_60": _quantile(speed_60, 0.75),
            "accel_std_30": _sample_std(accel_30),
        }
        if tuple(row) != FEATURE_NAMES:
            raise AssertionError("feature order does not match the model contract")
        output.append(row)
    return output

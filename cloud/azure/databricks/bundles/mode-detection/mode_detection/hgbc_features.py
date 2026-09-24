"""Exact 16-feature preprocessing contract for the robust AI-Hub HGBC model."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from .contract import Observation


HGBC_FEATURE_COLUMNS = (
    "distance_m",
    "displacement_m",
    "straightness_ratio",
    "mean_speed_mps",
    "max_speed_mps",
    "speed_std_mps",
    "mean_abs_acceleration_mps2",
    "acceleration_std_mps2",
    "stop_ratio",
    "mean_heading_change_deg",
    "altitude_range_m",
    "accuracy_mean_m",
    "accuracy_std_m",
    "accuracy_missing_ratio",
    "altitude_missing_ratio",
    "valid_point_ratio",
)

_EARTH_RADIUS_M = 6_371_008.8
_GAP_THRESHOLD_SECONDS = 120.0
_STOP_THRESHOLD_MPS = 0.5


def _pstdev(values: Sequence[float]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def _haversine_m(start: Observation, end: Observation) -> float:
    lat1 = math.radians(start.lat)
    lat2 = math.radians(end.lat)
    delta_lat = math.radians(end.lat - start.lat)
    delta_lon = math.radians(end.lon - start.lon)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return _EARTH_RADIUS_M * 2.0 * math.atan2(
        math.sqrt(value),
        math.sqrt(max(0.0, 1.0 - value)),
    )


def _bearing_deg(start: Observation, end: Observation) -> float:
    lat1 = math.radians(start.lat)
    lat2 = math.radians(end.lat)
    delta_lon = math.radians(end.lon - start.lon)
    x = math.sin(delta_lon) * math.cos(lat2)
    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _heading_change(previous: float, current: float) -> float:
    return abs((current - previous + 180.0) % 360.0 - 180.0)


def _validate(points: Sequence[Observation], raw_point_count: int) -> None:
    if len(points) < 2:
        raise ValueError("HGBC window requires at least two valid observations")
    if raw_point_count < len(points):
        raise ValueError("raw_point_count cannot be smaller than valid observation count")
    if raw_point_count <= 0:
        raise ValueError("raw_point_count must be positive")
    previous_sequence = None
    previous_time = None
    for point in points:
        if not math.isfinite(point.lat) or not math.isfinite(point.lon):
            raise ValueError("coordinates must be finite")
        if not -90.0 <= point.lat <= 90.0 or not -180.0 <= point.lon <= 180.0:
            raise ValueError("coordinate out of range")
        if previous_sequence is not None and point.sequence <= previous_sequence:
            raise ValueError("observations must have strictly increasing sequence")
        if previous_time is not None and point.event_time < previous_time:
            raise ValueError("observations must have non-decreasing event_time")
        previous_sequence = point.sequence
        previous_time = point.event_time


def compute_hgbc_features(
    observations: Sequence[Observation],
    *,
    raw_point_count: int,
) -> dict[str, float]:
    """Compute only features consumed by the robust HGBC artifact.

    The math intentionally mirrors the existing canonical AI-Hub feature code,
    while omitting the five cadence-sensitive outputs not consumed by the
    selected robust model.

    `raw_point_count` is explicit because validated Silver observations cannot,
    by themselves, distinguish dropped invalid source points. The streaming
    state layer must supply the raw count for the same window.
    """

    points = tuple(observations)
    _validate(points, raw_point_count)

    distances: list[float] = []
    speeds: list[float] = []
    accelerations: list[float] = []
    heading_changes: list[float] = []
    stop_flags: list[bool] = []

    previous_speed: float | None = None
    previous_bearing: float | None = None

    for start, end in zip(points, points[1:]):
        seconds = (end.event_time - start.event_time).total_seconds()
        distance = _haversine_m(start, end)

        if seconds <= 0.0 or seconds > _GAP_THRESHOLD_SECONDS:
            previous_speed = None
            previous_bearing = None
            continue

        speed = distance / seconds
        bearing = _bearing_deg(start, end)

        distances.append(distance)
        speeds.append(speed)
        stop_flags.append(speed <= _STOP_THRESHOLD_MPS)

        if previous_speed is not None:
            accelerations.append((speed - previous_speed) / seconds)
        if previous_bearing is not None:
            heading_changes.append(_heading_change(previous_bearing, bearing))

        previous_speed = speed
        previous_bearing = bearing

    displacement = _haversine_m(points[0], points[-1])
    distance = sum(distances)
    accuracy_values = [
        float(point.accuracy_m)
        for point in points
        if point.accuracy_m is not None
    ]

    # Match the training contract: missing altitude contributes 0 m to the
    # altitude series while altitude_missing_ratio records that it was absent.
    altitudes = [
        0.0 if point.altitude_m is None else float(point.altitude_m)
        for point in points
    ]
    altitude_missing_count = sum(point.altitude_m is None for point in points)

    result = {
        "distance_m": distance,
        "displacement_m": displacement,
        "straightness_ratio": displacement / distance if distance else 0.0,
        "mean_speed_mps": statistics.mean(speeds) if speeds else 0.0,
        "max_speed_mps": max(speeds, default=0.0),
        "speed_std_mps": _pstdev(speeds),
        "mean_abs_acceleration_mps2": (
            statistics.mean(abs(value) for value in accelerations)
            if accelerations
            else 0.0
        ),
        "acceleration_std_mps2": _pstdev(accelerations),
        "stop_ratio": statistics.mean(stop_flags) if stop_flags else 0.0,
        "mean_heading_change_deg": (
            statistics.mean(heading_changes) if heading_changes else 0.0
        ),
        "altitude_range_m": max(altitudes) - min(altitudes),
        "accuracy_mean_m": (
            statistics.mean(accuracy_values) if accuracy_values else 0.0
        ),
        "accuracy_std_m": _pstdev(accuracy_values),
        "accuracy_missing_ratio": 1.0 - len(accuracy_values) / len(points),
        "altitude_missing_ratio": altitude_missing_count / len(points),
        "valid_point_ratio": len(points) / raw_point_count,
    }
    return {name: float(result[name]) for name in HGBC_FEATURE_COLUMNS}

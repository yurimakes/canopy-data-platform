"""Incremental feature extraction over bounded GPS history."""

from __future__ import annotations

import math
from typing import Sequence

from .contracts import FEATURE_NAMES
from .feature_engineering import (
    GpsPoint,
    STOP_THRESHOLD_KMH,
    _bearing,
    _distance,
    _mean,
    _quantile,
    _sample_std,
)


class IncrementalFeatureExtractor:
    """Rebuild once from retained history, then emit only new feature rows."""

    def __init__(self, points: Sequence[GpsPoint] = ()) -> None:
        self.points: list[GpsPoint] = []
        self.speeds: list[float] = []
        self.accelerations: list[float] = []
        self.bearings: list[float] = []
        for point in points:
            self._append_kinematics(point)

    def _append_kinematics(self, point: GpsPoint) -> tuple[float, float, float, float]:
        index = len(self.points)
        if index == 0:
            dt = 0.1
            distance = 0.0
            bearing = 0.0
        else:
            previous = self.points[-1]
            dt = max((point.event_time - previous.event_time).total_seconds(), 0.1)
            distance = _distance(previous, point)
            bearing = _bearing(previous, point)

        speed = distance / dt * 3.6
        acceleration = 0.0 if index == 0 else (speed - self.speeds[-1]) / dt
        previous_bearing = 0.0 if index == 0 else self.bearings[-1]
        bearing_difference = abs(bearing - previous_bearing)
        bearing_change = (
            360.0 - bearing_difference
            if bearing_difference > 180.0
            else bearing_difference
        )

        self.points.append(point)
        self.speeds.append(speed)
        self.accelerations.append(acceleration)
        self.bearings.append(bearing)
        return speed, acceleration, distance, bearing_change

    def append(self, point: GpsPoint) -> dict[str, float]:
        speed, acceleration, distance, bearing_change = self._append_kinematics(point)

        speed_5 = self.speeds[-5:]
        speed_10 = self.speeds[-10:]
        speed_30 = self.speeds[-30:]
        speed_60 = self.speeds[-60:]
        speed_150 = self.speeds[-150:]
        accel_30 = self.accelerations[-30:]
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
        return row

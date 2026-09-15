"""Online rolling features shared by mock and future first-layer detectors."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
import math
from typing import Any, Mapping


class RollingSpeedMin:
    """Maintain the minimum speed in ``(event_time - lookback, event_time]``.

    State is isolated by trip. Inputs must already be deduplicated and ordered
    within each trip, matching the expected upstream Silver GPS contract.
    """

    def __init__(self, lookback: timedelta = timedelta(seconds=60)) -> None:
        if lookback <= timedelta(0):
            raise ValueError("lookback must be positive")
        self._lookback = lookback
        self._values: dict[str, deque[tuple[datetime, float]]] = defaultdict(deque)
        self._minima: dict[str, deque[tuple[datetime, float]]] = defaultdict(deque)
        self._last_event_time: dict[str, datetime] = {}

    def update(self, trip_id: str, event_time: datetime, speed_kmh: float) -> float:
        speed = float(speed_kmh)
        if not math.isfinite(speed) or not 0.0 <= speed <= 200.0:
            raise ValueError("speed_kmh must be finite and within [0, 200]")

        last_time = self._last_event_time.get(trip_id)
        if last_time is not None and event_time < last_time:
            raise ValueError(f"out-of-order event for trip {trip_id!r}")
        self._last_event_time[trip_id] = event_time

        values = self._values[trip_id]
        minima = self._minima[trip_id]
        cutoff = event_time - self._lookback

        while values and values[0][0] <= cutoff:
            expired = values.popleft()
            if minima and minima[0] == expired:
                minima.popleft()

        item = (event_time, speed)
        values.append(item)
        while minima and minima[-1][1] >= speed:
            minima.pop()
        minima.append(item)
        return minima[0][1]

    def clear_trip(self, trip_id: str) -> None:
        self._values.pop(trip_id, None)
        self._minima.pop(trip_id, None)
        self._last_event_time.pop(trip_id, None)

    def snapshot_trip(self, trip_id: str) -> dict[str, Any] | None:
        values = self._values.get(trip_id)
        if not values:
            return None
        return {
            "values": [
                {"event_time": event_time.isoformat(), "speed_kmh": speed}
                for event_time, speed in values
            ]
        }

    def restore_trip(self, trip_id: str, snapshot: Mapping[str, Any] | None) -> None:
        self.clear_trip(trip_id)
        if not snapshot:
            return
        for item in snapshot.get("values", ()):
            self.update(
                trip_id,
                datetime.fromisoformat(str(item["event_time"])),
                float(item["speed_kmh"]),
            )

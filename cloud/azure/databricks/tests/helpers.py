from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mode_inference.feature_engineering import GpsPoint


def trajectory(trip_id: str = "trip-a", count: int = 175) -> list[GpsPoint]:
    points = []
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lat = 37.5
    lon = 127.0
    for index in range(count):
        if index:
            current += timedelta(seconds=(1, 2, 5, 1, 3)[index % 5])
            if index % 17 not in (0, 1, 2):
                lat += (0.00002 + (index % 4) * 0.000005) * (-1 if index % 29 == 0 else 1)
                lon += (0.00003 + (index % 3) * 0.000004) * (-1 if index % 23 == 0 else 1)
        points.append(GpsPoint(
            event_id=f"{trip_id}-event-{index}",
            user_id=f"{trip_id}-user",
            trip_id=trip_id,
            sequence=index,
            event_time=current,
            lat=lat,
            lon=lon,
        ))
    return points


def row(point: GpsPoint) -> dict:
    return {
        "event_id": point.event_id,
        "user_id": point.user_id,
        "trip_id": point.trip_id,
        "sequence": point.sequence,
        "event_time": point.event_time,
        "lat": point.lat,
        "lon": point.lon,
    }

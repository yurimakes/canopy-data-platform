"""Spark 4 transformWithState adapter for ordered per-trip feature history."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

from .contracts import FEATURE_NAMES, FEATURE_OUTPUT_SCHEMA_DDL, MAX_RAW_POINTS
from .feature_engineering import GpsPoint, extract_features

try:
    from pyspark.sql.streaming import StatefulProcessor as _StatefulProcessor
except ImportError:  # pragma: no cover - keeps pure unit tests importable
    class _StatefulProcessor:  # type: ignore[no-redef]
        pass


STATE_SCHEMA = "state_json STRING NOT NULL"
STATE_VERSION = 1


def _value(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, Mapping) else getattr(row, name)


def _trip_id(key: Any) -> str:
    if isinstance(key, (tuple, list)):
        if len(key) != 1:
            raise ValueError("expected one trip_id key")
        return str(key[0])
    return str(key)


def _encode(points: list[GpsPoint], seen: set[str], last_sequence: int) -> str:
    return json.dumps({
        "version": STATE_VERSION,
        "last_sequence": last_sequence,
        "seen_event_ids": sorted(seen),
        "points": [
            {
                "event_id": point.event_id,
                "user_id": point.user_id,
                "trip_id": point.trip_id,
                "sequence": point.sequence,
                "event_time": point.event_time.isoformat(),
                "lat": point.lat,
                "lon": point.lon,
            }
            for point in points
        ],
    }, separators=(",", ":"), sort_keys=True)


def _decode(value: str) -> tuple[list[GpsPoint], set[str], int]:
    payload = json.loads(value)
    if payload.get("version") != STATE_VERSION:
        raise ValueError("unsupported trip-state version")
    points = [
        GpsPoint(
            event_id=item["event_id"], user_id=item["user_id"], trip_id=item["trip_id"],
            sequence=int(item["sequence"]), event_time=datetime.fromisoformat(item["event_time"]),
            lat=float(item["lat"]), lon=float(item["lon"]),
        )
        for item in payload["points"]
    ]
    return points, set(payload["seen_event_ids"]), int(payload["last_sequence"])


def point_from_row(row: Any) -> GpsPoint:
    return GpsPoint(
        event_id=str(_value(row, "event_id")),
        user_id=str(_value(row, "user_id")),
        trip_id=str(_value(row, "trip_id")),
        sequence=int(_value(row, "sequence")),
        event_time=_value(row, "event_time"),
        lat=float(_value(row, "lat")),
        lon=float(_value(row, "lon")),
    )


def advance_trip(
    trip_id: str,
    rows: Iterator[Any],
    points: list[GpsPoint] | None = None,
    seen_event_ids: set[str] | None = None,
    last_sequence: int = -1,
) -> tuple[list[dict[str, Any]], list[GpsPoint], set[str], int]:
    """Advance append-only state; rows late beyond the current sequence are ignored."""
    history = list(points or [])
    seen = set(seen_event_ids or set())
    outputs: list[dict[str, Any]] = []
    ordered = sorted(rows, key=lambda row: (
        int(_value(row, "sequence")), _value(row, "event_time"), str(_value(row, "event_id"))
    ))
    for row in ordered:
        point = point_from_row(row)
        if point.trip_id != trip_id:
            raise ValueError("grouping key does not match row trip_id")
        if point.event_id in seen or point.sequence <= last_sequence:
            continue
        history = history[-(MAX_RAW_POINTS - 1):]
        history.append(point)
        feature_values = extract_features(history)[-1]
        outputs.append({
            "event_id": point.event_id,
            "user_id": point.user_id,
            "trip_id": point.trip_id,
            "sequence": point.sequence,
            "event_time": point.event_time,
            **feature_values,
        })
        seen.add(point.event_id)
        last_sequence = point.sequence
        history = history[-MAX_RAW_POINTS:]
    return outputs, history, seen, last_sequence


class TripFeatureProcessor(_StatefulProcessor):
    def __init__(self, row_factory: Any = None) -> None:
        self._state: Any = None
        self._row_factory = row_factory

    def init(self, handle: Any) -> None:
        self._state = handle.getValueState("trip_feature_state", STATE_SCHEMA)

    def handleInputRows(self, key: Any, rows: Iterator[Any], timerValues: Any = None) -> Iterator[Any]:
        del timerValues
        trip_id = _trip_id(key)
        points: list[GpsPoint] = []
        seen: set[str] = set()
        last_sequence = -1
        if self._state.exists():
            points, seen, last_sequence = _decode(self._state.get()[0])
        outputs, points, seen, last_sequence = advance_trip(
            trip_id, rows, points, seen, last_sequence
        )
        if outputs:
            self._state.update((_encode(points, seen, last_sequence),))
        for values in outputs:
            if self._row_factory is not None:
                yield self._row_factory(**values)
            else:
                from pyspark.sql import Row
                yield Row(**values)

    def close(self) -> None:
        pass


def stateful_feature_rows(observations: Any, processor: TripFeatureProcessor | None = None) -> Any:
    return observations.groupBy("trip_id").transformWithState(
        statefulProcessor=processor or TripFeatureProcessor(),
        outputStructType=FEATURE_OUTPUT_SCHEMA_DDL,
        outputMode="Append",
        timeMode="None",
    )

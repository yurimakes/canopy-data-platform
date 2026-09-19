"""Spark 4 transformWithState adapter for ordered per-trip feature history."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any

from .contracts import FEATURE_NAMES, FEATURE_OUTPUT_SCHEMA_DDL, MAX_RAW_POINTS
from .feature_engineering import GpsPoint, extract_features

try:
    from pyspark.sql.streaming import StatefulProcessor as _StatefulProcessor
except ImportError:  # pragma: no cover - keeps pure unit tests importable
    class _StatefulProcessor:  # type: ignore[no-redef]
        pass


META_STATE_SCHEMA = "last_sequence BIGINT NOT NULL"
POINT_STATE_SCHEMA = (
    "event_id STRING NOT NULL, "
    "user_id STRING NOT NULL, "
    "trip_id STRING NOT NULL, "
    "sequence BIGINT NOT NULL, "
    "event_time TIMESTAMP NOT NULL, "
    "lat DOUBLE NOT NULL, "
    "lon DOUBLE NOT NULL"
)


def _value(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, Mapping) else getattr(row, name)


def _trip_id(key: Any) -> str:
    if isinstance(key, (tuple, list)):
        if len(key) != 1:
            raise ValueError("expected one trip_id key")
        return str(key[0])
    return str(key)


def _point_tuple(point: GpsPoint) -> tuple[Any, ...]:
    return (
        point.event_id,
        point.user_id,
        point.trip_id,
        point.sequence,
        point.event_time,
        point.lat,
        point.lon,
    )


def _point_from_state(value: Any) -> GpsPoint:
    return GpsPoint(
        event_id=str(value[0]),
        user_id=str(value[1]),
        trip_id=str(value[2]),
        sequence=int(value[3]),
        event_time=value[4],
        lat=float(value[5]),
        lon=float(value[6]),
    )


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
    """Advance append-only state with bounded point and duplicate history."""
    history = list(points or [])[-MAX_RAW_POINTS:]
    seen = set(seen_event_ids or {point.event_id for point in history})
    seen.intersection_update(point.event_id for point in history)
    outputs: list[dict[str, Any]] = []

    ordered = sorted(
        rows,
        key=lambda row: (
            int(_value(row, "sequence")),
            _value(row, "event_time"),
            str(_value(row, "event_id")),
        ),
    )
    for row in ordered:
        point = point_from_row(row)
        if point.trip_id != trip_id:
            raise ValueError("grouping key does not match row trip_id")
        if point.event_id in seen or point.sequence <= last_sequence:
            continue

        history = history[-(MAX_RAW_POINTS - 1):]
        history.append(point)
        feature_values = extract_features(history)[-1]
        outputs.append(
            {
                "event_id": point.event_id,
                "user_id": point.user_id,
                "trip_id": point.trip_id,
                "sequence": point.sequence,
                "event_time": point.event_time,
                "features_processed_at": datetime.now(timezone.utc),
                **feature_values,
            }
        )
        last_sequence = point.sequence
        history = history[-MAX_RAW_POINTS:]
        seen = {item.event_id for item in history}

    return outputs, history, seen, last_sequence


class TripFeatureProcessor(_StatefulProcessor):
    """Persist bounded native Spark state for one trip key."""

    def __init__(self, ttl_duration_ms: int, row_factory: Any = None) -> None:
        if ttl_duration_ms <= 0:
            raise ValueError("ttl_duration_ms must be positive")
        self._meta_state: Any = None
        self._point_state: Any = None
        self._ttl_duration_ms = ttl_duration_ms
        self._row_factory = row_factory

    def init(self, handle: Any) -> None:
        self._meta_state = handle.getValueState(
            "trip_feature_meta",
            META_STATE_SCHEMA,
            ttlDurationMs=self._ttl_duration_ms,
        )
        self._point_state = handle.getListState(
            "trip_feature_points",
            POINT_STATE_SCHEMA,
            ttlDurationMs=self._ttl_duration_ms,
        )

    def handleInputRows(
        self,
        key: Any,
        rows: Iterator[Any],
        timerValues: Any = None,
    ) -> Iterator[Any]:
        del timerValues
        trip_id = _trip_id(key)

        last_sequence = (
            int(self._meta_state.get()[0])
            if self._meta_state.exists()
            else -1
        )
        points = (
            [_point_from_state(value) for value in self._point_state.get()]
            if self._point_state.exists()
            else []
        )
        seen = {point.event_id for point in points}

        outputs, points, _seen, last_sequence = advance_trip(
            trip_id,
            rows,
            points,
            seen,
            last_sequence,
        )

        if outputs:
            self._meta_state.update((last_sequence,))
            # A single bounded rewrite resets TTL consistently for all retained
            # history rows and avoids per-point RocksDB writes.
            self._point_state.put([_point_tuple(point) for point in points])

        for values in outputs:
            if self._row_factory is not None:
                yield self._row_factory(**values)
            else:
                from pyspark.sql import Row

                yield Row(**values)

    def close(self) -> None:
        pass


def stateful_feature_rows(
    observations: Any,
    ttl_duration_ms: int,
    processor: TripFeatureProcessor | None = None,
) -> Any:
    return observations.groupBy("trip_id").transformWithState(
        statefulProcessor=processor or TripFeatureProcessor(ttl_duration_ms),
        outputStructType=FEATURE_OUTPUT_SCHEMA_DDL,
        outputMode="Append",
        timeMode="ProcessingTime",
    )

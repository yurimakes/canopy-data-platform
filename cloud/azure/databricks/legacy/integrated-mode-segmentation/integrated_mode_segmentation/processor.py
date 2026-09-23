"""Spark 4 transformWithState adapter for incremental trip segmentation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from .contracts import PROCESSOR_STATE_SCHEMA_DDL, SEGMENT_OUTPUT_SCHEMA_DDL
from .events import event_from_row
from .state_machine import PredictionPoint, TripEnd, TripSegmentationState

try:
    from pyspark.sql.streaming import StatefulProcessor as _StatefulProcessor
except ImportError:  # pragma: no cover - pure unit tests do not require Spark
    class _StatefulProcessor:  # type: ignore[no-redef]
        pass


_STATE_FIELDS = (
    "trip_id", "max_gap_seconds", "next_sequence", "pending", "fingerprints",
    "raw_window", "repaired_window", "completed_segments", "current_segment",
    "trip_ends", "ready_generations", "emitted_generations", "sealed_at", "conflicted",
)


def _trip_id(key: Any) -> str:
    if isinstance(key, (tuple, list)):
        if len(key) != 1:
            raise ValueError("expected one trip_id key")
        return str(key[0])
    return str(key)


def _state_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "asDict"):
        return value.asDict(recursive=True)
    if isinstance(value, (tuple, list)):
        return dict(zip(_STATE_FIELDS, value, strict=True))
    raise TypeError(f"unsupported state value: {type(value).__name__}")


def _state_tuple(state: TripSegmentationState) -> tuple[Any, ...]:
    values = state.to_state_dict()
    return tuple(values[name] for name in _STATE_FIELDS)


def _rows(iterator: Iterator[Any]) -> list[Any]:
    result: list[Any] = []
    for value in iterator:
        if hasattr(value, "to_dict") and hasattr(value, "columns"):
            result.extend(value.to_dict("records"))
        else:
            result.append(value)
    return result


class TripSegmentationProcessor(_StatefulProcessor):
    def __init__(
        self,
        ttl_duration_ms: int,
        max_gap_seconds: int = 3,
        now: Callable[[], datetime] | None = None,
        row_factory: Callable[..., Any] | None = None,
    ) -> None:
        if ttl_duration_ms <= 0:
            raise ValueError("ttl_duration_ms must be positive")
        self._ttl_duration_ms = ttl_duration_ms
        self._max_gap_seconds = max_gap_seconds
        self._now = now or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        self._row_factory = row_factory
        self._state: Any = None

    def init(self, handle: Any) -> None:
        self._state = handle.getValueState(
            "trip_segmentation_state",
            PROCESSOR_STATE_SCHEMA_DDL,
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
        state = (
            TripSegmentationState.from_state_dict(_state_mapping(self._state.get()))
            if self._state.exists()
            else TripSegmentationState(trip_id, self._max_gap_seconds)
        )
        if state.trip_id != trip_id:
            raise ValueError("stored state trip_id does not match grouping key")

        events = [event_from_row(row) for row in _rows(rows)]
        events.sort(
            key=lambda event: (
                0 if isinstance(event, PredictionPoint) else 1,
                event.sequence if isinstance(event, PredictionPoint) else event.expected_last_sequence,
                event.event_id,
            )
        )
        for event in events:
            if isinstance(event, PredictionPoint):
                state.accept_prediction(event)
            elif isinstance(event, TripEnd):
                state.accept_trip_end(event)

        outputs = state.drain_outputs(self._now())
        self._state.update(_state_tuple(state))
        for output in outputs:
            values = asdict(output)
            if self._row_factory is not None:
                yield self._row_factory(**values)
            else:
                from pyspark.sql import Row

                yield Row(**values)

    def close(self) -> None:
        pass


def stateful_segment_rows(
    events: Any,
    ttl_duration_ms: int,
    max_gap_seconds: int,
    processor: TripSegmentationProcessor | None = None,
) -> Any:
    return events.groupBy("trip_id").transformWithState(
        statefulProcessor=processor
        or TripSegmentationProcessor(ttl_duration_ms, max_gap_seconds),
        outputStructType=SEGMENT_OUTPUT_SCHEMA_DDL,
        outputMode="Append",
        timeMode="ProcessingTime",
    )

"""Spark 4 transformWithState bridge for the pure mode-detection state machine."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from .contract import Observation
from .hgbc import HGBCModeDetectingModel
from .legacy_transit import LegacyTransitContextResolver
from .lifecycle import TripEnded, TripLifecycleState
from .processing import ModeDetectionProcessor
from .segmentation import ModeSegment, SegmentState
from .spark_contracts import PROCESSOR_STATE_SCHEMA_DDL, SEALED_OUTPUT_SCHEMA_DDL
from .state import TripProcessingState
from .transit import TransitContextState

try:
    from pyspark.sql.streaming import StatefulProcessor as _StatefulProcessor
except ImportError:  # pragma: no cover
    class _StatefulProcessor:  # type: ignore[no-redef]
        pass


def _dt(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _value(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, Mapping) else getattr(row, name)


def _rows(iterator: Iterator[Any]) -> list[Any]:
    result: list[Any] = []
    for value in iterator:
        if hasattr(value, "to_dict") and hasattr(value, "columns"):
            result.extend(value.to_dict("records"))
        else:
            result.append(value)
    return result


def _trip_id(key: Any) -> str:
    if isinstance(key, (tuple, list)):
        if len(key) != 1:
            raise ValueError("expected one trip_id key")
        return str(key[0])
    return str(key)


def _observation_from_row(row: Any) -> Observation:
    return Observation(
        sequence=int(_value(row, "sequence")),
        event_time=_value(row, "event_time"),
        lat=float(_value(row, "lat")),
        lon=float(_value(row, "lon")),
        accuracy_m=(
            None if _value(row, "accuracy") is None else float(_value(row, "accuracy"))
        ),
        altitude_m=(
            None if _value(row, "altitude_m") is None else float(_value(row, "altitude_m"))
        ),
    )


def _trip_end_from_row(row: Any) -> TripEnded:
    return TripEnded(
        event_id=str(_value(row, "event_id")),
        trip_id=str(_value(row, "trip_id")),
        user_id=str(_value(row, "user_id")),
        campaign_id=str(_value(row, "campaign_id")),
        started_at=_value(row, "started_at"),
        ended_at=_value(row, "ended_at"),
        expected_last_sequence=int(_value(row, "expected_last_sequence")),
        occurred_at=_value(row, "occurred_at"),
        processing_generation=int(_value(row, "processing_generation")),
        result_owner=str(_value(row, "result_owner")),
    )


def _segment_dict(segment: ModeSegment) -> dict[str, Any]:
    return {
        "mode": segment.mode,
        "start_time": _iso(segment.start_time),
        "end_time": _iso(segment.end_time),
        "confidence": segment.confidence,
        "prediction_count": segment.prediction_count,
    }


def _segment_from_dict(value: Mapping[str, Any]) -> ModeSegment:
    return ModeSegment(
        mode=str(value["mode"]),
        start_time=_dt(value["start_time"]),
        end_time=_dt(value["end_time"]),
        confidence=float(value["confidence"]),
        prediction_count=int(value["prediction_count"]),
    )


def _trip_end_dict(event: TripEnded | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "event_id": event.event_id,
        "trip_id": event.trip_id,
        "user_id": event.user_id,
        "campaign_id": event.campaign_id,
        "started_at": _iso(event.started_at),
        "ended_at": _iso(event.ended_at),
        "expected_last_sequence": event.expected_last_sequence,
        "occurred_at": _iso(event.occurred_at),
        "processing_generation": event.processing_generation,
        "result_owner": event.result_owner,
    }


def _trip_end_from_dict(value: Mapping[str, Any] | None) -> TripEnded | None:
    if value is None:
        return None
    return TripEnded(
        event_id=str(value["event_id"]),
        trip_id=str(value["trip_id"]),
        user_id=str(value["user_id"]),
        campaign_id=str(value["campaign_id"]),
        started_at=_dt(value["started_at"]),
        ended_at=_dt(value["ended_at"]),
        expected_last_sequence=int(value["expected_last_sequence"]),
        occurred_at=_dt(value["occurred_at"]),
        processing_generation=int(value["processing_generation"]),
        result_owner=str(value["result_owner"]),
    )


def _snapshot(
    processor: ModeDetectionProcessor | None,
    lifecycle: TripLifecycleState,
    buffered_gps: list[Observation],
) -> str:
    payload: dict[str, Any] = {
        "trip_end": _trip_end_dict(lifecycle.trip_end),
        "emitted_generations": sorted(lifecycle.emitted_generations),
        "buffered_gps": [
            {
                "sequence": p.sequence,
                "event_time": _iso(p.event_time),
                "lat": p.lat,
                "lon": p.lon,
                "accuracy_m": p.accuracy_m,
                "altitude_m": p.altitude_m,
            }
            for p in buffered_gps
        ],
        "processor": None,
    }
    if processor is not None:
        payload["processor"] = {
            "trip_id": processor.trip.trip_id,
            "trip_start": _iso(processor.trip.trip_start),
            "last_prediction_end": _iso(processor.trip.last_prediction_end),
            "max_contiguous_sequence": processor.trip.max_contiguous_sequence,
            "pending_sequences": sorted(processor.trip.pending_sequences),
            "observations": [
                {
                    "sequence": p.sequence,
                    "event_time": _iso(p.event_time),
                    "lat": p.lat,
                    "lon": p.lon,
                    "accuracy_m": p.accuracy_m,
                    "altitude_m": p.altitude_m,
                }
                for p in processor.trip.observations
            ],
            "station_history": [list(item) for item in processor.transit.station_history],
            "completed_segments": [_segment_dict(s) for s in processor.segments.completed],
            "current_segment": (
                None if processor.segments.current is None
                else _segment_dict(processor.segments.current)
            ),
            "segments_sealed": processor.segments.sealed,
        }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _restore(payload: str | None):
    if not payload:
        return None, TripLifecycleState(), []
    data = json.loads(payload)
    lifecycle = TripLifecycleState(
        trip_end=_trip_end_from_dict(data.get("trip_end")),
        emitted_generations=set(int(v) for v in data.get("emitted_generations", [])),
    )
    buffered = [
        Observation(
            sequence=int(v["sequence"]),
            event_time=_dt(v["event_time"]),
            lat=float(v["lat"]),
            lon=float(v["lon"]),
            accuracy_m=None if v.get("accuracy_m") is None else float(v["accuracy_m"]),
            altitude_m=None if v.get("altitude_m") is None else float(v["altitude_m"]),
        )
        for v in data.get("buffered_gps", [])
    ]
    saved = data.get("processor")
    if saved is None:
        return None, lifecycle, buffered

    trip = TripProcessingState(
        trip_id=str(saved["trip_id"]),
        trip_start=_dt(saved["trip_start"]),
        last_prediction_end=_dt(saved.get("last_prediction_end")),
        max_contiguous_sequence=int(saved.get("max_contiguous_sequence", 0)),
        pending_sequences=set(int(v) for v in saved.get("pending_sequences", [])),
    )
    for value in saved.get("observations", []):
        point = Observation(
            sequence=int(value["sequence"]),
            event_time=_dt(value["event_time"]),
            lat=float(value["lat"]),
            lon=float(value["lon"]),
            accuracy_m=(
                None if value.get("accuracy_m") is None else float(value["accuracy_m"])
            ),
            altitude_m=(
                None if value.get("altitude_m") is None else float(value["altitude_m"])
            ),
        )
        trip.observations_by_sequence[point.sequence] = point

    transit = TransitContextState(
        station_history=[
            (str(item[0]), str(item[1]))
            for item in saved.get("station_history", [])
        ]
    )
    segments = SegmentState(
        trip_start=trip.trip_start,
        completed=[
            _segment_from_dict(v)
            for v in saved.get("completed_segments", [])
        ],
        current=(
            None
            if saved.get("current_segment") is None
            else _segment_from_dict(saved["current_segment"])
        ),
        sealed=bool(saved.get("segments_sealed", False)),
    )
    return ModeDetectionProcessor(trip, transit, segments), lifecycle, buffered


@lru_cache(maxsize=4)
def _runtime(
    artifact_path: str,
    stride_seconds: int,
    reference_root: str,
    transit_reference_dir: str,
):
    model = HGBCModeDetectingModel(
        artifact_path,
        prediction_stride_seconds=stride_seconds,
    )
    resolver = LegacyTransitContextResolver(
        reference_root=reference_root,
        transit_reference_dir=transit_reference_dir,
    )
    return model, resolver


class ModeDetectionStatefulProcessor(_StatefulProcessor):
    def __init__(
        self,
        *,
        ttl_duration_ms: int,
        artifact_path: str,
        prediction_stride_seconds: int,
        reference_root: str,
        transit_reference_dir: str,
        now=None,
        row_factory=None,
    ) -> None:
        if ttl_duration_ms <= 0:
            raise ValueError("ttl_duration_ms must be positive")
        self._ttl_duration_ms = ttl_duration_ms
        self._artifact_path = artifact_path
        self._prediction_stride_seconds = prediction_stride_seconds
        self._reference_root = reference_root
        self._transit_reference_dir = transit_reference_dir
        self._now = now or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        self._row_factory = row_factory
        self._state = None

    def init(self, handle: Any) -> None:
        self._state = handle.getValueState(
            "mode_detection_state",
            PROCESSOR_STATE_SCHEMA_DDL,
            ttlDurationMs=self._ttl_duration_ms,
        )

    def _state_payload(self) -> str | None:
        if not self._state.exists():
            return None
        value = self._state.get()
        if isinstance(value, Mapping):
            return value["payload"]
        if hasattr(value, "asDict"):
            return value.asDict()["payload"]
        return value[0]

    def handleInputRows(self, key: Any, rows: Iterator[Any], timerValues: Any = None):
        del timerValues
        trip_id = _trip_id(key)
        processor, lifecycle, buffered = _restore(self._state_payload())

        values = _rows(rows)
        values.sort(
            key=lambda row: (
                0 if _value(row, "event_kind") == "gps" else 1,
                (
                    int(_value(row, "sequence"))
                    if _value(row, "event_kind") == "gps"
                    else int(_value(row, "expected_last_sequence"))
                ),
            )
        )

        gps = [
            _observation_from_row(row)
            for row in values
            if _value(row, "event_kind") == "gps"
        ]
        trip_ends = [
            _trip_end_from_row(row)
            for row in values
            if _value(row, "event_kind") == "trip_end"
        ]

        if processor is None:
            buffered.extend(gps)
            sequence_one = next(
                (point for point in buffered if point.sequence == 1),
                None,
            )
            if sequence_one is not None:
                processor = ModeDetectionProcessor.for_trip(
                    trip_id,
                    sequence_one.event_time,
                )
                processor.trip.add_observations(buffered)
                buffered = []
        else:
            processor.trip.add_observations(gps)

        if processor is not None:
            for event in trip_ends:
                lifecycle.register_trip_end(event, processor=processor)
        elif trip_ends:
            if lifecycle.trip_end is None:
                lifecycle.trip_end = trip_ends[0]
            for event in trip_ends[1:]:
                if event != lifecycle.trip_end:
                    raise ValueError("conflicting trip_end event")

        outputs = []
        if processor is not None:
            model, resolver = _runtime(
                self._artifact_path,
                self._prediction_stride_seconds,
                self._reference_root,
                self._transit_reference_dir,
            )

            # Temporary fallback until raw-point provenance is wired through the
            # ingestion contract. This intentionally makes valid_point_ratio=1
            # for validated-only windows.
            raw_count = lambda _start, _end, points: len(points)

            processor.drain_due_mode_updates(
                model,
                raw_point_count_for_window=raw_count,
                transit_resolver=resolver,
            )
            sealed = lifecycle.seal_if_ready(
                processor,
                model,
                raw_point_count_for_window=raw_count,
                transit_resolver=resolver,
            )
            if sealed is not None:
                event = sealed.trip_end
                output = {
                    "trip_id": event.trip_id,
                    "user_id": event.user_id,
                    "campaign_id": event.campaign_id,
                    "processing_generation": event.processing_generation,
                    "started_at": event.started_at,
                    "ended_at": event.ended_at,
                    "expected_last_sequence": event.expected_last_sequence,
                    "segments": [
                        {
                            "mode": segment.mode,
                            "start_time": segment.start_time,
                            "end_time": segment.end_time,
                            "confidence": segment.confidence,
                            "prediction_count": segment.prediction_count,
                        }
                        for segment in sealed.segments
                    ],
                    "model_name": model.metadata.model_name,
                    "model_version": model.metadata.model_version,
                    "feature_version": model.metadata.feature_version,
                    "sealed_at": self._now(),
                }
                outputs.append(output)

        self._state.update((_snapshot(processor, lifecycle, buffered),))
        for output in outputs:
            if self._row_factory is not None:
                yield self._row_factory(**output)
            else:
                from pyspark.sql import Row
                yield Row(**output)

    def close(self) -> None:
        pass


def stateful_mode_detection_rows(
    events,
    *,
    ttl_duration_ms: int,
    artifact_path: str,
    prediction_stride_seconds: int,
    reference_root: str,
    transit_reference_dir: str,
    processor: ModeDetectionStatefulProcessor | None = None,
):
    return events.groupBy("trip_id").transformWithState(
        statefulProcessor=processor or ModeDetectionStatefulProcessor(
            ttl_duration_ms=ttl_duration_ms,
            artifact_path=artifact_path,
            prediction_stride_seconds=prediction_stride_seconds,
            reference_root=reference_root,
            transit_reference_dir=transit_reference_dir,
        ),
        outputStructType=SEALED_OUTPUT_SCHEMA_DDL,
        outputMode="Append",
        timeMode="ProcessingTime",
    )

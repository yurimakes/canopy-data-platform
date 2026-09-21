"""Stable boundary for Mock and the future ML/Transit Context pipeline."""
from datetime import datetime
from math import isfinite
from typing import Protocol, TypedDict

MODES = {"walk", "bike", "car", "bus", "rail"}


class FinalSegment(TypedDict):
    segment_id: str
    mode: str
    start_time: str
    end_time: str
    distance_m: float
    confidence: float | None


Segment = FinalSegment  # Compatibility with existing processor integrations.


class ProcessorResult(TypedDict):
    trip_id: str
    model_version: str
    segments: list[Segment]


class TripProcessor(Protocol):
    def process_trip(self, trip: dict) -> ProcessorResult:
        """Return final segments; do not write Trip state or modify GPS Raw.

        Implementations must be idempotent by trip_id + processing_generation:
        a host crash can cause the same durable job to be delivered again.
        expected_last_sequence is supplied by the phone after its GPS queue drains.
        Real processors must wait for Raw/Curated completeness (Capture can lag)
        and deduplicate event_id before deriving segments; the mock reads no GPS.
        """
        ...


class ProcessingError(Exception):
    def __init__(self, step: str, message: str):
        self.step = step
        super().__init__(message)


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def validate_result(trip: dict, result: ProcessorResult) -> None:
    """Only validate derived processor output. GPS ingestion remains untouched."""
    try:
        if result["trip_id"] != trip["trip_id"] or not isinstance(result["model_version"], str) or not result["model_version"].strip():
            raise ValueError("result identity/model_version mismatch")
        segments = result["segments"]
        quality=result.get('data_quality')
        if quality is not None:
            if not isinstance(quality,dict) or quality.get('status') not in ('complete','partial') or not isinstance(quality.get('version'),str) or not isinstance(quality.get('excluded_intervals'),list):
                raise ValueError('invalid data quality')
            if bool(quality['excluded_intervals'])!=(quality['status']=='partial'):raise ValueError('inconsistent data quality')
        endpoints=result.get('endpoint_observations')
        if endpoints is not None:
            if not isinstance(endpoints,list) or len(endpoints)!=2:raise ValueError('expected two endpoints')
            previous=timestamp(trip['started_at'])
            for point in endpoints:
                at=timestamp(point['event_time'])
                if not previous<=at<=timestamp(trip['ended_at']):raise ValueError('endpoint outside Trip')
                previous=at
                for key,bound in (('lat',90),('lon',180)):
                    v=point[key]
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or abs(v)>bound:raise ValueError('invalid endpoint')
        if not isinstance(segments, list) or not segments or len(segments) > 1000:
            raise ValueError("expected 1..1000 segments")
        seen = set()
        previous_end = timestamp(trip["started_at"])
        stop = timestamp(trip["ended_at"])
        for segment in segments:
            sid = segment["segment_id"]
            if not isinstance(sid, str) or not sid or sid in seen:
                raise ValueError("invalid/duplicate segment_id")
            seen.add(sid)
            begin, end = timestamp(segment["start_time"]), timestamp(segment["end_time"])
            if not previous_end <= begin <= end <= stop or segment["mode"] not in MODES:
                raise ValueError("invalid segment times/mode")
            for field in ("distance_m", "confidence"):
                value = segment[field]
                if field == "confidence" and value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                    raise ValueError("invalid " + field)
            if segment["confidence"] is not None and segment["confidence"] > 1:
                raise ValueError("confidence above 1")
            previous_end = end
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcessingError("validate_segments", str(exc)) from exc

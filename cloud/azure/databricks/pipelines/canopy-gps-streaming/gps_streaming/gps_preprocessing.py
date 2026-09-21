"""GPS observation parsing and train-aligned derived-speed preprocessing."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .mock_detector import SegmentEvent
from .pipeline import EnrichedSpeedPoint, MockFirstLayerPipeline
from .quality import transition_issue

EARTH_RADIUS_M = 6_371_000.0
MAX_SPEED_KMH = 200.0
SUPPORTED_SCHEMA_VERSION = "canopy.gps.collector.v0.1"


@dataclass(frozen=True)
class GpsObservation:
    schema_version: str
    event_id: str
    user_id: str
    device_id: str
    trip_id: str
    sequence: int
    event_time: datetime
    received_at: datetime
    lat: float
    lon: float
    accuracy: float | None
    speed: float | None
    altitude_m: float | None
    vertical_accuracy: float | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GpsObservation:
        """Parse the intended ``canopy.gps.collector.v0.1`` event contract."""
        required = (
            "schema_version",
            "event_id",
            "user_id",
            "device_id",
            "trip_id",
            "sequence",
            "event_time",
            "received_at",
            "lat",
            "lon",
        )
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(f"missing GPS fields: {missing}")
        if payload["schema_version"] not in (SUPPORTED_SCHEMA_VERSION,"canopy.gps.collector.v0.2"):
            raise ValueError(
                f"unsupported schema_version: {payload['schema_version']!r}"
            )

        event_time = _parse_timestamp(payload["event_time"], "event_time")
        received_at = _parse_timestamp(payload["received_at"], "received_at")
        lat = _finite_float(payload["lat"], "lat")
        lon = _finite_float(payload["lon"], "lon")
        if not -90.0 <= lat <= 90.0:
            raise ValueError("lat must be within [-90, 90]")
        if not -180.0 <= lon <= 180.0:
            raise ValueError("lon must be within [-180, 180]")

        sequence = int(payload["sequence"])
        if sequence < 0:
            raise ValueError("sequence must be non-negative")

        return cls(
            schema_version=str(payload["schema_version"]),
            event_id=str(payload["event_id"]),
            user_id=str(payload["user_id"]),
            device_id=str(payload["device_id"]),
            trip_id=str(payload["trip_id"]),
            sequence=sequence,
            event_time=event_time,
            received_at=received_at,
            lat=lat,
            lon=lon,
            accuracy=_optional_finite_float(payload.get("accuracy"), "accuracy"),
            # Preserve the producer value unchanged until its unit is confirmed.
            speed=_optional_finite_float(payload.get("speed"), "speed"),
            altitude_m=_optional_finite_float(payload.get("altitude_m"), "altitude_m"),
            vertical_accuracy=_optional_finite_float(
                payload.get("vertical_accuracy"), "vertical_accuracy"
            ),
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "trip_id": self.trip_id,
            "sequence": self.sequence,
            "event_time": self.event_time.isoformat(),
            "received_at": self.received_at.isoformat(),
            "lat": self.lat,
            "lon": self.lon,
            "accuracy": self.accuracy,
            "speed": self.speed,
            "altitude_m": self.altitude_m,
            "vertical_accuracy": self.vertical_accuracy,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> GpsObservation:
        return cls(
            schema_version=str(state["schema_version"]),
            event_id=str(state["event_id"]),
            user_id=str(state["user_id"]),
            device_id=str(state["device_id"]),
            trip_id=str(state["trip_id"]),
            sequence=int(state["sequence"]),
            event_time=datetime.fromisoformat(str(state["event_time"])),
            received_at=datetime.fromisoformat(str(state["received_at"])),
            lat=float(state["lat"]),
            lon=float(state["lon"]),
            accuracy=_optional_finite_float(state.get("accuracy"), "accuracy"),
            speed=_optional_finite_float(state.get("speed"), "speed"),
            altitude_m=_optional_finite_float(state.get("altitude_m"), "altitude_m"),
            vertical_accuracy=_optional_finite_float(
                state.get("vertical_accuracy"), "vertical_accuracy"
            ),
        )


@dataclass(frozen=True)
class DerivedGpsPoint:
    observation: GpsObservation
    previous_event_time: datetime | None
    dt_s: float | None
    distance_m: float | None
    derived_speed_kmh: float | None
    transition_valid: bool
    invalid_reason: str | None


@dataclass(frozen=True)
class GpsRuntimeOutput:
    point: DerivedGpsPoint
    enriched: EnrichedSpeedPoint | None
    segment: SegmentEvent | None
    discarded_partial_speed_points: int = 0


class GpsTransitionProcessor:
    """Derive speed from consecutive observations using their actual ``dt``."""

    def __init__(self) -> None:
        self._previous: dict[str, GpsObservation] = {}

    def process(self, observation: GpsObservation) -> DerivedGpsPoint:
        previous = self._previous.get(observation.trip_id)
        if previous is None:
            self._previous[observation.trip_id] = observation
            return DerivedGpsPoint(
                observation=observation,
                previous_event_time=None,
                dt_s=None,
                distance_m=None,
                derived_speed_kmh=None,
                transition_valid=False,
                invalid_reason="no_previous_observation",
            )

        dt_s = (observation.event_time - previous.event_time).total_seconds()
        if not math.isfinite(dt_s) or dt_s <= 0.0:
            # A late or duplicate event must not move the per-trip cursor
            # backwards and corrupt every following transition.
            return _invalid_transition(
                observation, previous.event_time, dt_s, "non_positive_dt"
            )

        self._previous[observation.trip_id] = observation
        distance_m = haversine_m(
            previous.lat, previous.lon, observation.lat, observation.lon
        )
        speed_kmh = distance_m / dt_s * 3.6
        issue=transition_issue(previous.accuracy,observation.accuracy,dt_s,speed_kmh)
        if issue:
            return _invalid_transition(observation,previous.event_time,dt_s,issue,distance_m)
        if not math.isfinite(speed_kmh):
            return _invalid_transition(
                observation,
                previous.event_time,
                dt_s,
                "non_finite_derived_speed",
                distance_m,
            )
        if speed_kmh > MAX_SPEED_KMH:
            return _invalid_transition(
                observation,
                previous.event_time,
                dt_s,
                "speed_above_200_kmh",
                distance_m,
            )

        return DerivedGpsPoint(
            observation=observation,
            previous_event_time=previous.event_time,
            dt_s=dt_s,
            distance_m=distance_m,
            derived_speed_kmh=speed_kmh,
            transition_valid=True,
            invalid_reason=None,
        )

    def clear_trip(self, trip_id: str) -> None:
        self._previous.pop(trip_id, None)

    def snapshot_trip(self, trip_id: str) -> dict[str, Any] | None:
        previous = self._previous.get(trip_id)
        return None if previous is None else previous.to_state()

    def restore_trip(self, trip_id: str, snapshot: Mapping[str, Any] | None) -> None:
        self.clear_trip(trip_id)
        if snapshot is not None:
            observation = GpsObservation.from_state(snapshot)
            if observation.trip_id != trip_id:
                raise ValueError("transition snapshot trip_id does not match state key")
            self._previous[trip_id] = observation


class GpsFirstLayerRuntime:
    """Connect point preprocessing to rolling features and mock segmentation."""

    def __init__(
        self,
        transition_processor: GpsTransitionProcessor | None = None,
        first_layer: MockFirstLayerPipeline | None = None,
    ) -> None:
        self.transition_processor = transition_processor or GpsTransitionProcessor()
        self.first_layer = first_layer or MockFirstLayerPipeline()

    def process(self, observation: GpsObservation) -> GpsRuntimeOutput:
        point = self.transition_processor.process(observation)
        if not point.transition_valid:
            discarded = 0
            if point.invalid_reason != "no_previous_observation":
                # Never allow a model window to bridge an invalid transition.
                discarded = self.first_layer.clear_trip(observation.trip_id)
            return GpsRuntimeOutput(
                point=point,
                enriched=None,
                segment=None,
                discarded_partial_speed_points=discarded,
            )

        enriched, segment = self.first_layer.process(
            trip_id=observation.trip_id,
            user_id=observation.user_id,
            event_time=observation.event_time,
            derived_speed_kmh=point.derived_speed_kmh,
        )
        return GpsRuntimeOutput(point=point, enriched=enriched, segment=segment)

    def clear_trip(self, trip_id: str) -> int:
        self.transition_processor.clear_trip(trip_id)
        return self.first_layer.clear_trip(trip_id)

    def snapshot_trip(self, trip_id: str) -> dict[str, Any]:
        return {
            "version": 1,
            "previous_observation": self.transition_processor.snapshot_trip(trip_id),
            "first_layer": self.first_layer.snapshot_trip(trip_id),
        }

    def restore_trip(self, trip_id: str, snapshot: Mapping[str, Any]) -> None:
        if int(snapshot.get("version", 0)) != 1:
            raise ValueError("unsupported GPS runtime state version")
        self.transition_processor.restore_trip(
            trip_id, snapshot.get("previous_observation")
        )
        self.first_layer.restore_trip(trip_id, snapshot.get("first_layer"))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance using the training pipeline's Earth radius."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _invalid_transition(
    observation: GpsObservation,
    previous_event_time: datetime,
    dt_s: float,
    reason: str,
    distance_m: float | None = None,
) -> DerivedGpsPoint:
    return DerivedGpsPoint(
        observation=observation,
        previous_event_time=previous_event_time,
        dt_s=dt_s,
        distance_m=distance_m,
        derived_speed_kmh=None,
        transition_valid=False,
        invalid_reason=reason,
    )


def _parse_timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO-8601") from exc
    else:
        raise TypeError(f"{field} must be datetime or ISO-8601 string")
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return result


def _finite_float(value: Any, field: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_finite_float(value: Any, field: str) -> float | None:
    return None if value is None else _finite_float(value, field)

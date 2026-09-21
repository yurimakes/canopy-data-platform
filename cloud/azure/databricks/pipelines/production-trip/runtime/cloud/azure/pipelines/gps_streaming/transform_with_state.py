"""Spark 4 row-based ``transformWithState`` adapter for per-trip GPS state."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .deployment_config import CanopyTableConfig
from .gps_preprocessing import GpsFirstLayerRuntime, GpsObservation, GpsRuntimeOutput
from .mock_detector import MockDetectorConfig, MockFirstLayerDetector
from .pipeline import MockFirstLayerPipeline

try:  # Keep the neutral package and its unit tests importable without PySpark.
    from pyspark.sql.streaming import StatefulProcessor as _StatefulProcessor
except ImportError:  # pragma: no cover - exercised by the local non-Spark suite

    class _StatefulProcessor:  # type: ignore[no-redef]
        pass


TRIP_STATE_SCHEMA = "state_json STRING NOT NULL"
STATE_VERSION = 1

# A tagged union lets one stateful operator atomically advance its checkpoint,
# while foreachBatch routes idempotent rows to the two public Delta contracts.
STATEFUL_OUTPUT_SCHEMA = """
  record_type STRING NOT NULL,
  schema_version STRING,
  event_id STRING,
  user_id STRING,
  device_id STRING,
  trip_id STRING NOT NULL,
  sequence BIGINT,
  event_time TIMESTAMP,
  received_at TIMESTAMP,
  lat DOUBLE,
  lon DOUBLE,
  accuracy DOUBLE,
  raw_speed DOUBLE,
  altitude_m DOUBLE,
  vertical_accuracy DOUBLE,
  previous_event_time TIMESTAMP,
  dt_s DOUBLE,
  distance_m DOUBLE,
  derived_speed_kmh DOUBLE,
  transition_valid BOOLEAN,
  invalid_reason STRING,
  speed_min_60s DOUBLE,
  segment_id STRING,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  speed_point_count INT,
  weak_mode STRING,
  weak_confidence DOUBLE,
  status STRING,
  detector_version STRING,
  processed_at TIMESTAMP NOT NULL
"""

FEATURE_COLUMNS = (
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
    "accuracy",
    "raw_speed",
    "altitude_m",
    "vertical_accuracy",
    "previous_event_time",
    "dt_s",
    "distance_m",
    "derived_speed_kmh",
    "transition_valid",
    "invalid_reason",
    "speed_min_60s",
    "processed_at",
)

SEGMENT_COLUMNS = (
    "trip_id",
    "user_id",
    "segment_id",
    "start_time",
    "end_time",
    "speed_point_count",
    "weak_mode",
    "weak_confidence",
    "status",
    "detector_version",
    "processed_at",
)


@dataclass(frozen=True)
class TransformWithStateConfig:
    checkpoint_location: str
    tables: CanopyTableConfig = field(default_factory=CanopyTableConfig)
    query_name: str = "canopy-gps-features-and-segments"

    def __post_init__(self) -> None:
        if not self.checkpoint_location.strip():
            raise ValueError("transformWithState checkpoint location is required")


class CanopyGpsStatefulProcessor(_StatefulProcessor):
    """Restore, advance, and persist one neutral runtime for each trip key."""

    def __init__(
        self,
        detector_config: MockDetectorConfig | None = None,
        *,
        row_factory: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.detector_config = detector_config or MockDetectorConfig()
        self._row_factory = row_factory
        self._clock = clock or _utc_now
        self._trip_state: Any = None

    def init(self, handle: Any) -> None:
        self._trip_state = handle.getValueState("canopy_trip_state", TRIP_STATE_SCHEMA)

    def handleInputRows(
        self, key: Any, rows: Iterator[Any], timerValues: Any = None
    ) -> Iterator[Any]:
        del timerValues  # This processor deliberately uses TimeMode.None.
        trip_id = _trip_id_from_key(key)
        runtime = self._new_runtime()
        if self._trip_state.exists():
            runtime.restore_trip(trip_id, decode_trip_state(self._trip_state.get()[0]))

        ordered_rows = sorted(
            rows,
            key=lambda row: (
                _row_value(row, "event_time"),
                int(_row_value(row, "sequence")),
                str(_row_value(row, "event_id")),
            ),
        )
        for row in ordered_rows:
            observation = observation_from_row(row)
            if observation.trip_id != trip_id:
                raise ValueError("grouping key does not match observation trip_id")
            processed_at = self._clock()
            output = runtime.process(observation)
            yield self._make_row(feature_record(output, processed_at))
            if output.segment is not None:
                yield self._make_row(segment_record(output, processed_at))

        if ordered_rows:
            self._trip_state.update(
                (encode_trip_state(runtime.snapshot_trip(trip_id)),)
            )

    def close(self) -> None:
        pass

    def _new_runtime(self) -> GpsFirstLayerRuntime:
        detector = MockFirstLayerDetector(self.detector_config)
        return GpsFirstLayerRuntime(
            first_layer=MockFirstLayerPipeline(detector=detector)
        )

    def _make_row(self, values: Mapping[str, Any]) -> Any:
        if self._row_factory is not None:
            return self._row_factory(**values)
        from pyspark.sql import Row

        return Row(**values)


def encode_trip_state(snapshot: Mapping[str, Any]) -> str:
    envelope = {"state_version": STATE_VERSION, "runtime": snapshot}
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True)


def decode_trip_state(value: str) -> Mapping[str, Any]:
    envelope = json.loads(value)
    if int(envelope.get("state_version", 0)) != STATE_VERSION:
        raise ValueError("unsupported transformWithState envelope version")
    runtime = envelope.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError(  # noqa: TRY004
            "transformWithState runtime state must be an object"
        )
    return runtime



def observation_from_row(row: Any) -> GpsObservation:
    return GpsObservation(
        schema_version=str(_row_value(row, "schema_version")),
        event_id=str(_row_value(row, "event_id")),
        user_id=str(_row_value(row, "user_id")),
        device_id=str(_row_value(row, "device_id")),
        trip_id=str(_row_value(row, "trip_id")),
        sequence=int(_row_value(row, "sequence")),
        event_time=_row_value(row, "event_time"),
        received_at=_row_value(row, "received_at"),
        lat=float(_row_value(row, "lat")),
        lon=float(_row_value(row, "lon")),
        accuracy=_optional_float(_row_value(row, "accuracy")),
        speed=_optional_float(_row_value(row, "raw_speed")),
        altitude_m=_optional_float(_row_value(row, "altitude_m")),
        vertical_accuracy=_optional_float(_row_value(row, "vertical_accuracy")),
    )


def feature_record(output: GpsRuntimeOutput, processed_at: datetime) -> dict[str, Any]:
    point = output.point
    observation = point.observation
    values = _empty_record("feature", observation.trip_id, processed_at)
    values.update(
        schema_version=observation.schema_version,
        event_id=observation.event_id,
        user_id=observation.user_id,
        device_id=observation.device_id,
        sequence=observation.sequence,
        event_time=observation.event_time,
        received_at=observation.received_at,
        lat=observation.lat,
        lon=observation.lon,
        accuracy=observation.accuracy,
        raw_speed=observation.speed,
        altitude_m=observation.altitude_m,
        vertical_accuracy=observation.vertical_accuracy,
        previous_event_time=point.previous_event_time,
        dt_s=point.dt_s,
        distance_m=point.distance_m,
        derived_speed_kmh=point.derived_speed_kmh,
        transition_valid=point.transition_valid,
        invalid_reason=point.invalid_reason,
        speed_min_60s=None
        if output.enriched is None
        else output.enriched.speed_min_60s,
    )
    return values


def segment_record(output: GpsRuntimeOutput, processed_at: datetime) -> dict[str, Any]:
    segment = output.segment
    if segment is None:
        raise ValueError("segment output is required")
    values = _empty_record("segment", segment.trip_id, processed_at)
    values.update(
        user_id=segment.user_id,
        segment_id=segment.segment_id,
        start_time=segment.start_time,
        end_time=segment.end_time,
        speed_point_count=segment.speed_point_count,
        weak_mode=segment.weak_mode,
        weak_confidence=segment.weak_confidence,
        status=segment.status,
        detector_version=segment.detector_version,
    )
    return values


def stateful_rows(
    observations: Any, processor: CanopyGpsStatefulProcessor | None = None
) -> Any:
    """Attach the DBR 17.3 Python Row transform to a streaming DataFrame."""
    return observations.groupBy("trip_id").transformWithState(
        statefulProcessor=processor or CanopyGpsStatefulProcessor(),
        outputStructType=STATEFUL_OUTPUT_SCHEMA,
        outputMode="Append",
        timeMode="None",
    )


def start_stateful_stream(
    spark: Any,
    config: TransformWithStateConfig,
    *,
    trigger_interval: str = "10 seconds",
) -> Any:
    outputs = stateful_rows(spark.readStream.table(config.tables.observations_table))
    handler = build_stateful_batch_handler(config)
    return (
        outputs.writeStream.queryName(config.query_name)
        .option("checkpointLocation", config.checkpoint_location)
        .trigger(processingTime=trigger_interval)
        .foreachBatch(handler)
        .start()
    )


def build_stateful_batch_handler(
    config: TransformWithStateConfig,
) -> Callable[[Any, int], None]:
    """Build a retry-safe router from tagged rows to feature and segment tables."""

    def handler(batch: Any, batch_id: int) -> None:
        del batch_id
        from delta.tables import DeltaTable
        from pyspark.sql import functions as F

        features = batch.where(F.col("record_type") == "feature").select(
            *FEATURE_COLUMNS
        )
        if not features.isEmpty():
            (
                DeltaTable.forName(batch.sparkSession, config.tables.features_table)
                .alias("target")
                .merge(features.alias("source"), "target.event_id = source.event_id")
                .whenNotMatchedInsertAll()
                .execute()
            )

        segments = (
            batch.where(F.col("record_type") == "segment")
            .select(*SEGMENT_COLUMNS)
            .withColumnRenamed("processed_at", "emitted_at")
        )
        if not segments.isEmpty():
            (
                DeltaTable.forName(batch.sparkSession, config.tables.segments_table)
                .alias("target")
                .merge(
                    segments.alias("source"), "target.segment_id = source.segment_id"
                )
                .whenNotMatchedInsertAll()
                .execute()
            )

    return handler


def _empty_record(
    record_type: str, trip_id: str, processed_at: datetime
) -> dict[str, Any]:
    fields = [
        line.strip().split()[0]
        for line in STATEFUL_OUTPUT_SCHEMA.splitlines()
        if line.strip()
    ]
    values = {field.rstrip(","): None for field in fields}
    values.update(record_type=record_type, trip_id=trip_id, processed_at=processed_at)
    return values


def _trip_id_from_key(key: Any) -> str:
    if isinstance(key, (tuple, list)):
        if len(key) != 1:
            raise ValueError("expected exactly one transformWithState grouping key")
        return str(key[0])
    return str(key)


def _row_value(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row[name]
    return getattr(row, name)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

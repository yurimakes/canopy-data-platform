"""Trial Lakeflow definition for finalized-trip segment generation."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

from segment_generation.segmentation import (
    build_ready_points,
    build_segments,
    stabilize_predictions,
)


def _spark() -> SparkSession:
    session = SparkSession.getActiveSession()
    if session is None:
        raise RuntimeError("Lakeflow pipeline requires an active SparkSession")
    return session


def _conf(name: str) -> str:
    value = _spark().conf.get(f"canopy.{name}")
    if not value or not value.strip():
        raise ValueError(f"missing Lakeflow pipeline configuration: canopy.{name}")
    return value.strip()


CATALOG = _conf("catalog")
SCHEMA = _conf("schema")

TRIP_ENDED_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('trip_ended_table')}"
GPS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('gps_observations_table')}"
PREDICTIONS_TABLE = f"{CATALOG}.{SCHEMA}.{_conf('mode_predictions_table')}"
SEGMENTS_TABLE = _conf("segments_table")
MAX_REPAIR_GAP_SECONDS = int(_conf("max_repair_gap_seconds"))


@dp.materialized_view(
    name=SEGMENTS_TABLE,
    comment=(
        "Deterministic finalized-trip mode segments derived from validated GPS "
        "observations and pointwise mode predictions."
    ),
)
def mode_segments() -> DataFrame:
    ready = build_ready_points(
        _spark().read.table(TRIP_ENDED_TABLE),
        _spark().read.table(GPS_TABLE),
        _spark().read.table(PREDICTIONS_TABLE),
    )
    stabilized = stabilize_predictions(ready, MAX_REPAIR_GAP_SECONDS)
    return build_segments(stabilized)

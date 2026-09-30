from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest


pytestmark = pytest.mark.spark


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    if shutil.which("java") is None:
        pytest.skip("local Spark JVM is unavailable")
    from pyspark.sql import SparkSession

    session = SparkSession.builder.master("local[1]").appName(
        "integrated-mode-segmentation-contracts"
    ).getOrCreate()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def test_union_normalization_has_one_stable_schema(spark) -> None:
    from integrated_mode_segmentation.events import unified_events

    predictions = spark.createDataFrame(
        [
            (
                "p1", "u1", "t1", 1, datetime(2026, 9, 20), 37.0, 127.0,
                "walk", None, "m", "1", datetime(2026, 9, 20),
            )
        ],
        "event_id string, user_id string, trip_id string, sequence long, "
        "event_time timestamp, lat double, lon double, predicted_mode string, "
        "confidence double, model_name string, model_version string, predicted_at timestamp",
    )
    trip_ends = spark.createDataFrame(
        [("e1", "u1", "t1", 1, 1, datetime(2026, 9, 20), "databricks")],
        "event_id string, user_id string, trip_id string, expected_last_sequence long, "
        "processing_generation long, parsed_at timestamp, result_owner string",
    )

    rows = unified_events(predictions, trip_ends).orderBy("event_kind").collect()
    assert {row.event_kind for row in rows} == {"prediction", "trip_end"}
    assert len(rows[0].asDict()) == len(rows[1].asDict()) == 17


def test_processor_state_tuple_matches_declared_spark_schema(spark) -> None:
    from pyspark.sql.types import StructType

    from integrated_mode_segmentation.contracts import PROCESSOR_STATE_SCHEMA_DDL
    from integrated_mode_segmentation.processor import _state_tuple
    from integrated_mode_segmentation.state_machine import (
        PredictionPoint,
        TripSegmentationState,
    )

    state = TripSegmentationState("t1", 3)
    state.accept_prediction(
        PredictionPoint(
            "p1", "u1", "t1", 1, datetime(2026, 9, 20), 37.0, 127.0,
            "walk", None, "m", "1", datetime(2026, 9, 20),
        )
    )
    schema = StructType.fromDDL(PROCESSOR_STATE_SCHEMA_DDL)
    row = spark.createDataFrame([_state_tuple(state)], schema).collect()[0]
    restored = TripSegmentationState.from_state_dict(row)
    assert restored.to_state_dict() == state.to_state_dict()


def test_fractional_gap_behavior_matches_existing_spark_reference(spark) -> None:
    segment_project = Path(__file__).resolve().parents[2] / "segment-generation"
    sys.path.insert(0, str(segment_project))
    try:
        from segment_generation.segmentation import stabilize_predictions
    finally:
        sys.path.remove(str(segment_project))

    rows = [
        ("t1", 1, "p1", 1, datetime(2026, 9, 20, 0, 0, 0, 100_000), "car"),
        ("t1", 1, "p2", 2, datetime(2026, 9, 20, 0, 0, 3, 900_000), "walk"),
        ("t1", 1, "p3", 3, datetime(2026, 9, 20, 0, 0, 4, 900_000), "car"),
    ]
    points = spark.createDataFrame(
        rows,
        "trip_id string, processing_generation long, event_id string, sequence long, "
        "event_time timestamp, predicted_mode string",
    )
    reference = [
        row.stabilized_mode
        for row in stabilize_predictions(points, 3).orderBy("sequence").collect()
    ]
    assert reference == ["car", "car", "car"]

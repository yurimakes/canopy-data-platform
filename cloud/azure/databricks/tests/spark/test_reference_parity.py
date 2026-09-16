from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mode_inference.contracts import FEATURE_NAMES, MAX_RAW_POINTS
from mode_inference.feature_engineering import extract_features
from mode_inference.state import advance_trip
from tests.helpers import row, trajectory
from tests.reference_preprocessing import extract_advanced_features_v3

pytestmark = pytest.mark.spark


def reference(points):
    frame = pd.DataFrame({
        "trip_id": [point.trip_id for point in points],
        "timestamp": [point.event_time.timestamp() * 1000.0 for point in points],
        "latitude": [point.lat for point in points],
        "longitude": [point.lon for point in points],
    })
    return extract_advanced_features_v3(frame)


@pytest.mark.parametrize("count", [1, 2, 4, 6, 11, 31, 61, 151, 176])
def test_all_17_features_match_pandas_reference(count):
    points = trajectory(count=count)
    actual = pd.DataFrame(extract_features(points))
    expected = reference(points)
    for feature in FEATURE_NAMES:
        np.testing.assert_allclose(actual[feature], expected[feature], rtol=1e-9, atol=1e-8)


def test_state_rollover_matches_reference_past_150_points():
    points = trajectory(count=176)
    first, history, seen, last_sequence = advance_trip(
        points[0].trip_id, iter(row(point) for point in points[:97])
    )
    second, history, seen, last_sequence = advance_trip(
        points[0].trip_id, iter(row(point) for point in reversed(points[97:])),
        history, seen, last_sequence,
    )
    actual = pd.DataFrame(first + second)
    expected = reference(points)
    assert len(history) == MAX_RAW_POINTS
    for feature in FEATURE_NAMES:
        np.testing.assert_allclose(actual[feature], expected[feature], rtol=1e-9, atol=1e-8)
    for feature in ("speed_mean_150", "stop_count_150", "speed_q25_60", "speed_q75_60", "accel_std_30"):
        assert actual.iloc[-1][feature] == pytest.approx(expected.iloc[-1][feature], rel=1e-9, abs=1e-8)


def test_trip_isolation_and_simultaneous_trip_ids():
    left = trajectory("left", 70)
    right = trajectory("right", 70)
    left_output, *_ = advance_trip("left", iter(row(point) for point in reversed(left)))
    right_output, *_ = advance_trip("right", iter(row(point) for point in reversed(right)))
    assert {item["trip_id"] for item in left_output} == {"left"}
    assert {item["trip_id"] for item in right_output} == {"right"}
    assert left_output[0]["speed"] == right_output[0]["speed"] == 0.0

import pytest

from mode_inference.contracts import FEATURE_NAMES
from mode_inference.feature_engineering import extract_features
from tests.helpers import trajectory


def test_first_point_semantics():
    feature = extract_features(trajectory(count=1))[0]
    assert tuple(feature) == FEATURE_NAMES
    assert feature["speed"] == 0.0
    assert feature["distance"] == 0.0
    assert feature["acceleration"] == 0.0
    assert feature["bearing_change"] == 0.0
    assert feature["stop_count_150"] == 1.0
    assert feature["accel_std_30"] == 0.0


@pytest.mark.parametrize("count", [2, 3, 4, 6, 11, 31, 61, 151, 176])
def test_history_boundaries_produce_finite_features(count):
    result = extract_features(trajectory(count=count))
    assert len(result) == count
    assert all(value == value for feature in result for value in feature.values())

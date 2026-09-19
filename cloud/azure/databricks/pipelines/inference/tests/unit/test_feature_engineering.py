import pytest

from mode_inference.contracts import FEATURE_NAMES
from mode_inference.feature_engineering import extract_features
from mode_inference.incremental_features import IncrementalFeatureExtractor
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


@pytest.mark.parametrize("count", [1, 2, 5, 10, 31, 61, 151, 176, 220])
def test_incremental_extractor_matches_reference(count):
    points = trajectory(count=count)
    reference = extract_features(points)
    extractor = IncrementalFeatureExtractor()
    incremental = [extractor.append(point) for point in points]

    assert len(incremental) == len(reference)
    for expected, actual in zip(reference, incremental):
        assert tuple(actual) == FEATURE_NAMES
        for name in FEATURE_NAMES:
            assert actual[name] == pytest.approx(expected[name], rel=1e-12, abs=1e-12)


def test_incremental_extractor_rebuilds_history_then_appends():
    points = trajectory(count=180)
    retained = points[:151]
    extractor = IncrementalFeatureExtractor(retained)
    actual = extractor.append(points[151])
    expected = extract_features(points[:152])[-1]

    for name in FEATURE_NAMES:
        assert actual[name] == pytest.approx(expected[name], rel=1e-12, abs=1e-12)

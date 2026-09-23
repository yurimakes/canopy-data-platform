from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mode_detection.contract import Observation
from mode_detection.hgbc_features import HGBC_FEATURE_COLUMNS, compute_hgbc_features


def point(
    sequence: int,
    seconds: int,
    lat: float,
    lon: float,
    *,
    accuracy: float | None = 5.0,
    altitude: float | None = 10.0,
) -> Observation:
    return Observation(
        sequence=sequence,
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        lat=lat,
        lon=lon,
        accuracy_m=accuracy,
        altitude_m=altitude,
    )


def test_feature_contract_is_exactly_16_robust_inputs():
    assert len(HGBC_FEATURE_COLUMNS) == 16
    assert set(HGBC_FEATURE_COLUMNS).isdisjoint(
        {
            "point_count",
            "observed_duration_sec",
            "avg_sampling_interval_sec",
            "valid_step_count",
            "gap_step_count",
        }
    )


def test_feature_extractor_returns_only_model_inputs():
    points = [
        point(1, 0, 37.0, 127.0, altitude=None),
        point(2, 10, 37.0001, 127.0001, accuracy=None, altitude=15.0),
        point(3, 20, 37.0002, 127.0002, altitude=20.0),
    ]
    result = compute_hgbc_features(points, raw_point_count=4)

    assert tuple(result) == HGBC_FEATURE_COLUMNS
    assert result["valid_point_ratio"] == pytest.approx(0.75)
    assert result["accuracy_missing_ratio"] == pytest.approx(1 / 3)
    assert result["altitude_missing_ratio"] == pytest.approx(1 / 3)
    assert result["altitude_range_m"] == pytest.approx(20.0)
    assert result["distance_m"] > 0
    assert result["displacement_m"] > 0


def test_gap_resets_speed_history_without_becoming_a_valid_step():
    points = [
        point(1, 0, 37.0, 127.0),
        point(2, 10, 37.0001, 127.0001),
        point(3, 200, 37.0010, 127.0010),
        point(4, 210, 37.0011, 127.0011),
    ]
    result = compute_hgbc_features(points, raw_point_count=4)

    assert result["distance_m"] > 0
    assert result["mean_abs_acceleration_mps2"] == pytest.approx(0.0)


def test_raw_point_count_is_not_implicitly_valid_count():
    points = [
        point(1, 0, 37.0, 127.0),
        point(2, 10, 37.0001, 127.0001),
    ]
    with pytest.raises(ValueError, match="raw_point_count"):
        compute_hgbc_features(points, raw_point_count=1)

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from mode_detection.contract import Observation
from mode_detection.hgbc import HGBCModeDetectingModel
from mode_detection.hgbc_features import HGBC_FEATURE_COLUMNS


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeModel:
    def __init__(self):
        self.frames = []

    def predict_proba(self, frame):
        self.frames.append(frame.copy())
        return np.asarray([[0.1, 0.2, 0.6, 0.05, 0.05]])


def observation(sequence: int, seconds: int) -> Observation:
    return Observation(
        sequence=sequence,
        event_time=BASE + timedelta(seconds=seconds),
        lat=37.0 + sequence * 0.00001,
        lon=127.0 + sequence * 0.00001,
        accuracy_m=5.0,
        altitude_m=10.0,
    )


def bundle(model=None):
    return {
        "model": model or FakeModel(),
        "feature_columns": list(HGBC_FEATURE_COLUMNS),
        "classes": ["bike", "bus", "car", "rail", "walk"],
        "feature_version": "aihub-canonical-raw120-v2",
        "window_duration_seconds": 120,
        "selected_candidate": "c3_hgb_robust_cadence",
    }


def build(bundle_value=None, stride=10):
    return HGBCModeDetectingModel(
        "/unused/model.joblib",
        prediction_stride_seconds=stride,
        bundle_loader=lambda _: bundle_value or bundle(),
    )


def test_metadata_uses_configured_stride():
    model = build(stride=15)
    assert model.metadata.window_seconds == 120
    assert model.metadata.prediction_stride_seconds == 15
    assert model.metadata.model_version == "c3_hgb_robust_cadence"


def test_prediction_requires_data_through_scheduled_window():
    model = build()
    points = [observation(1, 0), observation(2, 119)]
    assert not model.prediction_ready(points, window_end=BASE + timedelta(seconds=120))

    points.append(observation(3, 120))
    assert model.prediction_ready(points, window_end=BASE + timedelta(seconds=120))


def test_prediction_tolerates_phone_jitter_inside_complete_window():
    model = build()
    window_end = BASE + timedelta(seconds=120)

    # Reproduce the real-phone shape: the last point selected for the first
    # 120-second window lands 379 ms before the scheduled boundary, while a
    # later observation proves that the boundary has actually elapsed.
    points = [
        Observation(
            sequence=sequence + 1,
            event_time=BASE + timedelta(seconds=seconds),
            lat=37.0 + sequence * 0.00001,
            lon=127.0 + sequence * 0.00001,
            accuracy_m=5.0,
            altitude_m=10.0,
        )
        for sequence, seconds in enumerate(
            [*(float(value) for value in range(120)), 119.621, 120.5]
        )
    ]

    assert model.prediction_ready(points, window_end=window_end)
    prediction = model.predict(
        points,
        window_end=window_end,
        raw_point_count=121,
    )
    assert prediction.window_end == window_end


def test_predict_uses_exact_16_feature_order_and_scheduled_window_end():
    estimator = FakeModel()
    model = build(bundle(estimator))
    points = [
        observation(1, 0),
        observation(2, 60),
        observation(3, 120),
        observation(4, 123),
    ]

    prediction = model.predict(
        points,
        window_end=BASE + timedelta(seconds=120),
        raw_point_count=3,
    )

    assert prediction.predicted_mode == "car"
    assert prediction.confidence == pytest.approx(0.6)
    assert prediction.window_start == BASE
    assert prediction.window_end == BASE + timedelta(seconds=120)
    assert tuple(estimator.frames[0].columns) == HGBC_FEATURE_COLUMNS


def test_future_observations_do_not_shift_scheduled_window():
    model = build()
    points = [
        observation(1, 0),
        observation(2, 10),
        observation(3, 120),
        observation(4, 130),
    ]

    prediction = model.predict(
        points,
        window_end=BASE + timedelta(seconds=120),
        raw_point_count=3,
    )

    assert prediction.window_start == BASE
    assert prediction.window_end == BASE + timedelta(seconds=120)


def test_rejects_non_robust_artifact_contract():
    bad = bundle()
    bad["feature_columns"] = [*HGBC_FEATURE_COLUMNS, "point_count"]
    with pytest.raises(ValueError, match="feature contract"):
        build(bad)

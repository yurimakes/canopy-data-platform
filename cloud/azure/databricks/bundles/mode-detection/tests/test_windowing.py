from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mode_detection.windowing import scheduled_prediction_ends, terminal_segment_end


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_first_prediction_requires_full_120_seconds():
    assert scheduled_prediction_ends(
        BASE,
        BASE + timedelta(seconds=119),
        window_seconds=120,
        stride_seconds=10,
    ) == []

    assert scheduled_prediction_ends(
        BASE,
        BASE + timedelta(seconds=120),
        window_seconds=120,
        stride_seconds=10,
    ) == [BASE + timedelta(seconds=120)]


def test_stride_is_parameterized():
    assert scheduled_prediction_ends(
        BASE,
        BASE + timedelta(seconds=150),
        window_seconds=120,
        stride_seconds=15,
    ) == [
        BASE + timedelta(seconds=120),
        BASE + timedelta(seconds=135),
        BASE + timedelta(seconds=150),
    ]


def test_resume_from_last_prediction_end():
    assert scheduled_prediction_ends(
        BASE,
        BASE + timedelta(seconds=151),
        window_seconds=120,
        stride_seconds=10,
        last_prediction_end=BASE + timedelta(seconds=140),
    ) == [BASE + timedelta(seconds=150)]


def test_trip_end_extends_last_mode_over_short_tail():
    assert terminal_segment_end(
        last_prediction_end=BASE + timedelta(seconds=720),
        trip_end=BASE + timedelta(seconds=723),
        stride_seconds=10,
    ) == BASE + timedelta(seconds=723)


def test_trip_end_requires_all_due_predictions_drained():
    with pytest.raises(ValueError, match="undrained"):
        terminal_segment_end(
            last_prediction_end=BASE + timedelta(seconds=720),
            trip_end=BASE + timedelta(seconds=730),
            stride_seconds=10,
        )

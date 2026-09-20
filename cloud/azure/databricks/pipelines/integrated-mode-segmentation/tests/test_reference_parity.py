from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from integrated_mode_segmentation.state_machine import (
    EARTH_RADIUS_M,
    PredictionPoint,
    TripEnd,
    TripSegmentationState,
)


BASE = datetime(2026, 9, 20, tzinfo=timezone.utc)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _within(left: PredictionPoint, right: PredictionPoint, maximum: int) -> bool:
    seconds = (right.event_time - left.event_time).total_seconds()
    return 0 <= seconds <= maximum


def _reference_modes(points: list[PredictionPoint], maximum: int) -> list[str]:
    predicted = [point.predicted_mode for point in points]
    repaired = list(predicted)
    for index in range(len(points)):
        if (
            index >= 2
            and index + 1 < len(points)
            and predicted[index - 2] == predicted[index]
            and predicted[index - 1] == predicted[index + 1]
            and predicted[index - 1] != predicted[index]
            and _within(points[index - 2], points[index - 1], maximum)
            and _within(points[index - 1], points[index], maximum)
            and _within(points[index], points[index + 1], maximum)
        ):
            repaired[index] = predicted[index - 1]

    stabilized = list(repaired)
    for index in range(1, len(points) - 1):
        if (
            repaired[index - 1] == repaired[index + 1]
            and repaired[index] != repaired[index - 1]
            and _within(points[index - 1], points[index], maximum)
            and _within(points[index], points[index + 1], maximum)
        ):
            stabilized[index] = repaired[index - 1]
    return stabilized


def _distance(left: PredictionPoint, right: PredictionPoint) -> float:
    lat1 = math.radians(left.lat)
    lat2 = math.radians(right.lat)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(right.lon - left.lon)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, value)))


def _reference_segments(points: list[PredictionPoint], maximum: int):
    modes = _reference_modes(points, maximum)
    groups: list[list[tuple[PredictionPoint, str]]] = []
    for point, mode in zip(points, modes, strict=True):
        if not groups or groups[-1][-1][1] != mode:
            groups.append([])
        groups[-1].append((point, mode))

    result = []
    for group in groups:
        values = [value[0] for value in group]
        result.append(
            {
                "mode": group[0][1],
                "start_sequence": values[0].sequence,
                "end_sequence": values[-1].sequence,
                "start_time": _utc_naive(values[0].event_time),
                "end_time": _utc_naive(values[-1].event_time),
                "point_count": len(values),
                "distance_m": sum(
                    _distance(left, right)
                    for left, right in zip(values, values[1:])
                ),
                "model_name": min(value.model_name for value in values),
                "model_version": min(
                    (value.model_version for value in values if value.model_version is not None),
                    default=None,
                ),
                "latest_prediction_at": _utc_naive(max(value.predicted_at for value in values)),
            }
        )
    return result


def _points(modes: list[str], gaps: list[int]) -> list[PredictionPoint]:
    current = BASE
    result = []
    for sequence, (mode, gap) in enumerate(zip(modes, gaps, strict=True), start=1):
        current += timedelta(seconds=gap)
        result.append(
            PredictionPoint(
                event_id=f"event-{sequence}",
                user_id="user-1",
                trip_id="trip-1",
                sequence=sequence,
                event_time=current,
                lat=37.0 + sequence / 100_000,
                lon=127.0 + sequence / 100_000,
                predicted_mode=mode,
                confidence=None,
                model_name="model-b" if sequence % 2 else "model-a",
                model_version=None if sequence % 3 == 0 else "2",
                predicted_at=current + timedelta(milliseconds=sequence),
            )
        )
    return result


def _incremental(points: list[PredictionPoint], maximum: int):
    state = TripSegmentationState("trip-1", max_gap_seconds=maximum)
    for point in points:
        state.accept_prediction(point)
    state.accept_trip_end(
        TripEnd("end-1", "trip-1", "user-1", len(points), 1, BASE, "databricks")
    )
    return state.drain_outputs(BASE + timedelta(hours=1))


@pytest.mark.parametrize(
    ("modes", "gaps"),
    [
        (["car"] * 5, [0, 1, 1, 1, 1]),
        (["walk", "walk", "car", "car"], [0, 1, 1, 1]),
        (["car", "car", "car", "walk", "car", "walk", "walk"], [0] + [1] * 6),
        (["car", "walk", "car"], [0, 10, 1]),
    ],
)
def test_incremental_output_matches_independent_batch_reference(modes, gaps) -> None:
    points = _points(modes, gaps)
    expected = _reference_segments(points, 3)
    actual = _incremental(points, 3)

    assert len(actual) == len(expected)
    for row, reference in zip(actual, expected, strict=True):
        for field in reference.keys() - {"distance_m"}:
            assert getattr(row, field) == reference[field]
        assert row.distance_m == pytest.approx(reference["distance_m"], abs=1e-9)


def test_seeded_mode_and_gap_sequences_match_reference() -> None:
    rng = random.Random(20260920)
    for length in range(1, 40):
        modes = [rng.choice(["walk", "bike", "car", "bus"]) for _ in range(length)]
        gaps = [0] + [rng.choice([1, 1, 2, 4]) for _ in range(length - 1)]
        points = _points(modes, gaps)
        expected = _reference_segments(points, 3)
        actual = _incremental(points, 3)
        assert [(row.mode, row.start_sequence, row.end_sequence) for row in actual] == [
            (row["mode"], row["start_sequence"], row["end_sequence"])
            for row in expected
        ]
        assert [row.distance_m for row in actual] == pytest.approx(
            [row["distance_m"] for row in expected], abs=1e-9
        )

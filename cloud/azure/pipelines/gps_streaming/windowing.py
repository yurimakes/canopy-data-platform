"""Build representative SpeedTransformer windows from a closed segment."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

SEQUENCE_LENGTH = 200


@dataclass(frozen=True)
class SpeedWindow:
    """One model window and its location in the closed segment."""

    window_index: int
    start_index: int
    end_index: int
    speed_sequence: tuple[float, ...]


def target_window_count(speed_point_count: int) -> int:
    """Return the initial representative-window policy for one segment."""
    if speed_point_count < SEQUENCE_LENGTH:
        return 0
    if speed_point_count < 250:
        return 1
    if speed_point_count < 350:
        return 3
    if speed_point_count < 600:
        return 5
    if speed_point_count < 1_000:
        return 7
    return 10


def representative_start_indices(length: int, count: int) -> tuple[int, ...]:
    """Evenly cover a sequence while always touching its first and last item."""
    if length < SEQUENCE_LENGTH:
        return ()
    if count <= 0:
        raise ValueError("count must be positive for an eligible sequence")

    last_start = length - SEQUENCE_LENGTH
    if count == 1 or last_start == 0:
        return (0,)

    # More requested windows than distinct starts should not create duplicates.
    count = min(count, last_start + 1)
    starts = {round(index * last_start / (count - 1)) for index in range(count)}
    return tuple(sorted(starts))


def build_speed_windows(
    speeds_kmh: Iterable[float],
    *,
    window_count: int | None = None,
) -> tuple[SpeedWindow, ...]:
    """Validate physical speeds and build the MLflow model's 200-value rows."""
    speeds = tuple(float(value) for value in speeds_kmh)
    for value in speeds:
        if not math.isfinite(value) or not 0.0 <= value <= 200.0:
            raise ValueError("all speeds must be finite and within [0, 200] km/h")

    requested = (
        target_window_count(len(speeds)) if window_count is None else window_count
    )
    starts = representative_start_indices(len(speeds), requested)
    return tuple(
        SpeedWindow(
            window_index=index,
            start_index=start,
            end_index=start + SEQUENCE_LENGTH - 1,
            speed_sequence=speeds[start : start + SEQUENCE_LENGTH],
        )
        for index, start in enumerate(starts)
    )

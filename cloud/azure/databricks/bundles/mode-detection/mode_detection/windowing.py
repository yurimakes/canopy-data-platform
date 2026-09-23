"""Prediction scheduling and trip-end tail semantics."""

from __future__ import annotations

from datetime import datetime, timedelta


def scheduled_prediction_ends(
    trip_start: datetime,
    latest_observation_time: datetime,
    *,
    window_seconds: int,
    stride_seconds: int,
    last_prediction_end: datetime | None = None,
) -> list[datetime]:
    """Return due stride-aligned prediction end times.

    The first prediction is due at trip_start + window_seconds. Subsequent
    predictions advance by stride_seconds. Only full model windows are
    scheduled; there is no fractional-window readiness rule.
    """

    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if stride_seconds <= 0:
        raise ValueError("stride_seconds must be positive")
    if latest_observation_time < trip_start:
        raise ValueError("latest observation precedes trip start")

    first = trip_start + timedelta(seconds=window_seconds)
    if latest_observation_time < first:
        return []

    if last_prediction_end is None:
        next_end = first
    else:
        if last_prediction_end < first:
            raise ValueError("last prediction end precedes first valid prediction")
        next_end = last_prediction_end + timedelta(seconds=stride_seconds)

    due: list[datetime] = []
    while next_end <= latest_observation_time:
        due.append(next_end)
        next_end += timedelta(seconds=stride_seconds)
    return due


def terminal_segment_end(
    *,
    last_prediction_end: datetime,
    trip_end: datetime,
    stride_seconds: int,
) -> datetime:
    """Close the active segment at trip end without inventing a partial prediction.

    Once all scheduled predictions due through the final GPS observation have
    been drained, the remaining tail is shorter than one stride. The last known
    mode is extended to trip_end.

    A different terminal prediction is not retroactively applied to this tail;
    that would violate the window-end decision semantics.
    """

    if stride_seconds <= 0:
        raise ValueError("stride_seconds must be positive")
    if trip_end < last_prediction_end:
        raise ValueError("trip end precedes last prediction")

    tail_seconds = (trip_end - last_prediction_end).total_seconds()
    if tail_seconds >= stride_seconds:
        raise ValueError("undrained scheduled prediction exists before trip end")
    return trip_end

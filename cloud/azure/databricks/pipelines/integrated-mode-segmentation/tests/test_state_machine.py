from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from integrated_mode_segmentation.state_machine import (
    PredictionPoint,
    TripEnd,
    TripSegmentationState,
)


BASE = datetime(2026, 9, 20, tzinfo=timezone.utc)


def point(
    sequence: int,
    mode: str = "car",
    *,
    event_id: str | None = None,
    lat: float = 37.0,
    lon: float | None = None,
) -> PredictionPoint:
    return PredictionPoint(
        event_id=event_id or f"event-{sequence}",
        user_id="user-1",
        trip_id="trip-1",
        sequence=sequence,
        event_time=BASE + timedelta(seconds=sequence - 1),
        lat=lat,
        lon=127.0 + sequence / 10_000 if lon is None else lon,
        predicted_mode=mode,
        confidence=None,
        model_name="model-a",
        model_version="1",
        predicted_at=BASE + timedelta(seconds=sequence),
    )


def trip_end(last: int, generation: int = 1, *, event_id: str | None = None) -> TripEnd:
    return TripEnd(
        event_id=event_id or f"end-{generation}",
        trip_id="trip-1",
        user_id="user-1",
        expected_last_sequence=last,
        processing_generation=generation,
        parsed_at=BASE + timedelta(minutes=generation),
        result_owner="databricks",
    )


def finalize(modes: list[str], max_gap_seconds: int = 3):
    state = TripSegmentationState("trip-1", max_gap_seconds=max_gap_seconds)
    for sequence, mode in enumerate(modes, start=1):
        state.accept_prediction(point(sequence, mode))
    state.accept_trip_end(trip_end(len(modes)))
    return state, state.drain_outputs(BASE + timedelta(minutes=2))


def test_all_same_mode_builds_one_segment() -> None:
    _, rows = finalize(["car", "car", "car"])

    assert [(r.segment_index, r.mode, r.start_sequence, r.end_sequence) for r in rows] == [
        (1, "car", 1, 3)
    ]
    assert rows[0].point_count == 3
    assert rows[0].segment_id == "trip-1:g1:segment:1"


def test_single_and_multiple_transitions_build_ordered_segments() -> None:
    _, rows = finalize(["walk", "walk", "car", "car", "bus", "bus"])

    assert [(r.mode, r.start_sequence, r.end_sequence) for r in rows] == [
        ("walk", 1, 2),
        ("car", 3, 4),
        ("bus", 5, 6),
    ]


@pytest.mark.parametrize(
    ("modes", "expected"),
    [
        (["car", "car", "car", "walk", "car", "car", "car"], [("car", 1, 7)]),
        (
            ["car", "car", "car", "walk", "car", "walk", "walk", "walk"],
            [("car", 1, 3), ("walk", 4, 8)],
        ),
    ],
)
def test_smoothing_matches_singleton_and_transition_lag_rules(modes, expected) -> None:
    _, rows = finalize(modes)
    assert [(r.mode, r.start_sequence, r.end_sequence) for r in rows] == expected


def test_trip_end_before_final_prediction_waits_for_contiguous_completion() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(2))
    state.accept_trip_end(trip_end(3))
    state.accept_prediction(point(1))

    assert state.drain_outputs(BASE) == []

    state.accept_prediction(point(3))
    rows = state.drain_outputs(BASE)
    assert [(r.start_sequence, r.end_sequence) for r in rows] == [(1, 3)]


def test_missing_prefix_never_finalizes() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(2))
    state.accept_prediction(point(3))
    state.accept_trip_end(trip_end(3))
    assert state.drain_outputs(BASE) == []


def test_exact_replay_is_ignored_even_after_compaction() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    original = point(1)
    state.accept_prediction(original)
    state.accept_prediction(original)
    state.accept_trip_end(trip_end(1))

    assert len(state.drain_outputs(BASE)) == 1
    assert not state.conflicted


def test_conflicting_payload_for_same_sequence_invalidates_trip() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(1, "car"))
    state.accept_prediction(point(1, "walk", event_id="different-event"))
    state.accept_trip_end(trip_end(1))

    assert state.conflicted
    assert state.drain_outputs(BASE) == []



def test_trip_end_replay_with_new_parsed_at_is_ignored() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(1))

    first = trip_end(1)
    replay = TripEnd(
        **{
            **first.__dict__,
            "parsed_at": first.parsed_at + timedelta(seconds=30),
        }
    )

    state.accept_trip_end(first)
    rows = state.drain_outputs(BASE)
    state.accept_trip_end(replay)

    assert len(rows) == 1
    assert state.drain_outputs(BASE + timedelta(seconds=30)) == []
    assert not state.conflicted


def test_conflicting_trip_end_for_generation_invalidates_trip() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(1))
    state.accept_trip_end(trip_end(1))
    state.accept_trip_end(trip_end(2, event_id="conflicting-end"))

    assert state.conflicted
    assert state.drain_outputs(BASE) == []


def test_generation_two_emits_new_deterministic_ids_and_each_generation_once() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    for sequence in range(1, 4):
        state.accept_prediction(point(sequence))

    first = trip_end(3, generation=1)
    state.accept_trip_end(first)
    first_rows = state.drain_outputs(BASE)
    state.accept_trip_end(first)
    assert state.drain_outputs(BASE) == []

    state.accept_trip_end(trip_end(3, generation=2))
    second_rows = state.drain_outputs(BASE)
    assert [r.segment_id for r in first_rows] == ["trip-1:g1:segment:1"]
    assert [r.segment_id for r in second_rows] == ["trip-1:g2:segment:1"]


def test_distance_counts_only_edges_inside_each_final_segment() -> None:
    state, rows = finalize(["walk", "walk", "car", "car"])
    del state

    assert len(rows) == 2
    assert rows[0].distance_m > 0
    assert rows[1].distance_m > 0
    assert rows[0].distance_m == pytest.approx(rows[1].distance_m, rel=1e-3)


def test_gap_larger_than_policy_prevents_singleton_repair() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(1, "car"))
    state.accept_prediction(
        PredictionPoint(**{**point(2, "walk").as_dict(), "event_time": BASE + timedelta(seconds=20)})
    )
    state.accept_prediction(
        PredictionPoint(**{**point(3, "car").as_dict(), "event_time": BASE + timedelta(seconds=21)})
    )
    state.accept_trip_end(trip_end(3))

    assert [r.mode for r in state.drain_outputs(BASE)] == ["car", "walk", "car"]


def test_fractional_timestamp_gaps_match_spark_unix_timestamp_truncation() -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    timestamps = [
        BASE + timedelta(milliseconds=100),
        BASE + timedelta(seconds=3, milliseconds=900),
        BASE + timedelta(seconds=4, milliseconds=900),
    ]
    for sequence, (mode, timestamp) in enumerate(
        zip(["car", "walk", "car"], timestamps, strict=True), start=1
    ):
        source = point(sequence, mode)
        state.accept_prediction(
            PredictionPoint(**{**source.as_dict(), "event_time": timestamp})
        )
    state.accept_trip_end(trip_end(3))

    assert [(row.mode, row.start_sequence, row.end_sequence) for row in state.drain_outputs(BASE)] == [
        ("car", 1, 3)
    ]


@pytest.mark.parametrize("owners", [("databricks", "functions"), ("functions", "databricks")])
def test_changing_trip_end_owner_is_a_conflict_before_finalization(owners) -> None:
    state = TripSegmentationState("trip-1", max_gap_seconds=3)
    state.accept_prediction(point(1))
    for index, owner in enumerate(owners):
        event = trip_end(2, event_id=f"owner-{index}")
        state.accept_trip_end(
            TripEnd(**{**event.__dict__, "result_owner": owner})
        )
    state.accept_prediction(point(2))

    assert state.conflicted
    assert state.drain_outputs(BASE) == []

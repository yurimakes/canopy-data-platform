from datetime import timezone

from mode_inference.contracts import MAX_RAW_POINTS
from mode_inference.state import advance_trip, point_state_delta
from tests.helpers import row, trajectory


def test_orders_sequence_and_suppresses_duplicate_and_late_rows():
    points = trajectory(count=4)
    incoming = [row(points[2]), row(points[0]), row(points[1]), row(points[1])]
    output, history, seen, last_sequence = advance_trip(points[0].trip_id, iter(incoming))
    assert [item["sequence"] for item in output] == [0, 1, 2]
    assert len(seen) == 3
    assert last_sequence == 2
    late = dict(row(points[3]), sequence=1, event_id="late-new-id")
    output, _, _, _ = advance_trip(points[0].trip_id, iter([late]), history, seen, last_sequence)
    assert output == []


def test_state_keeps_151_raw_points_and_rolls_forward():
    points = trajectory(count=180)
    output, history, seen, last_sequence = advance_trip(points[0].trip_id, iter(map(row, points)))
    assert len(output) == 180
    assert len(history) == MAX_RAW_POINTS
    assert history[0].sequence == 29
    assert len(seen) == MAX_RAW_POINTS
    assert seen == {point.event_id for point in history}
    assert last_sequence == 179


def test_mixed_state_and_input_timestamp_timezone_normalizes_before_features():
    points = trajectory(count=3)
    state_history = [
        points[0].__class__(
            event_id=points[0].event_id,
            user_id=points[0].user_id,
            trip_id=points[0].trip_id,
            sequence=points[0].sequence,
            event_time=points[0].event_time.astimezone(timezone.utc).replace(tzinfo=None),
            lat=points[0].lat,
            lon=points[0].lon,
        )
    ]
    output, history, seen, last_sequence = advance_trip(
        points[0].trip_id,
        iter([row(points[1]), row(points[2])]),
        points=state_history,
        seen_event_ids={state_history[0].event_id},
        last_sequence=0,
    )
    assert [item["sequence"] for item in output] == [1, 2]
    assert len(history) == 3
    assert len(seen) == 3
    assert last_sequence == 2


def test_point_state_delta_only_mutates_new_and_expired_window_entries():
    points = trajectory(count=161)
    previous = points[:151]
    retained = points[10:161]

    additions, removals = point_state_delta(
        {point.sequence for point in previous},
        retained,
    )

    assert [point.sequence for point in additions] == list(range(151, 161))
    assert removals == set(range(10))
    assert len(additions) == 10
    assert len(removals) == 10

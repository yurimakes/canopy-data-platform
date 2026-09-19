from mode_inference.contracts import MAX_RAW_POINTS
from mode_inference.state import advance_trip
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

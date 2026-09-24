from datetime import datetime, timezone

from complete_payload.finalize_trip import segment_distances


def p(seq, second, lat, lon):
    return {
        "sequence": seq,
        "event_time": datetime(2026, 1, 1, 0, 0, second, tzinfo=timezone.utc),
        "lat": lat,
        "lon": lon,
    }


def test_boundary_leg_is_counted_once():
    points = [
        p(1, 0, 37.0, 127.0),
        p(2, 5, 37.0, 127.001),
        p(3, 10, 37.0, 127.002),
    ]
    segments = [
        {
            "start_time": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        },
        {
            "start_time": datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            "end_time": datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
        },
    ]
    distances = segment_distances(points, segments)
    assert distances[0] > 0
    assert distances[1] > 0
    assert abs(distances[0] - distances[1]) < 1e-6

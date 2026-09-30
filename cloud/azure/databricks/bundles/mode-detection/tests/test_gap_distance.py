from datetime import datetime, timedelta, timezone

from mode_detection.contract import Observation
from mode_detection.distance import DistanceState

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_distance_does_not_count_leg_across_outage():
    state = DistanceState()
    points = [Observation(sequence=i, event_time=BASE + timedelta(seconds=t), lat=37.0, lon=127.0 + i * 0.01, accuracy_m=5.0, altitude_m=10.0) for i, t in [(1, 0), (2, 60), (3, 61)]]
    state.add_observations(points, gps_gap_tolerance_seconds=15)
    assert len(state.legs) == 1
    assert state.legs[0].end_time == BASE + timedelta(seconds=61)

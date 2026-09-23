"""Synthetic integration-test results. No GPS inference or measured distance."""
from datetime import timedelta
from .trip_processor import ProcessorResult, timestamp


class MockTripProcessor:
    def process_trip(self, trip: dict) -> ProcessorResult:
        start, end = timestamp(trip["started_at"]), timestamp(trip["ended_at"])
        duration = (end - start).total_seconds()
        modes = [("walk", 1.0, 1.2)] if duration < 300 else [
            ("walk", .2, 1.2), ("bus", .6, 6.0), ("walk", .2, 1.2)]
        segments = []
        cursor = start
        for index, (mode, fraction, fake_speed) in enumerate(modes):
            next_time = end if index == len(modes) - 1 else cursor + timedelta(seconds=duration * fraction)
            segments.append({
                "segment_id": f"{trip['trip_id']}:segment:{index + 1}",
                "mode": mode, "start_time": cursor.isoformat(), "end_time": next_time.isoformat(),
                "distance_m": round((next_time - cursor).total_seconds() * fake_speed, 2),
                "confidence": 0.0,
            })
            cursor = next_time
        return {"trip_id": trip["trip_id"], "model_version": "mock_v1", "segments": segments}


class ConfirmationFixtureProcessor:
    """Short-trip phone fixture: walk 500m, bus 6200m, walk 300m. Never measured GPS."""
    def process_trip(self, trip: dict) -> ProcessorResult:
        start, end = timestamp(trip["started_at"]), timestamp(trip["ended_at"])
        duration = end - start
        cuts = [start, start + duration * .2, start + duration * .8, end]
        return {"trip_id": trip["trip_id"], "model_version": "mock_v1", "segments": [
            {"segment_id": f"{trip['trip_id']}:segment:{i+1}", "mode": mode,
             "start_time": cuts[i].isoformat(), "end_time": cuts[i+1].isoformat(),
             "distance_m": distance, "confidence": 0.0}
            for i, (mode, distance) in enumerate([("walk", 500), ("bus", 6200), ("walk", 300)])]}

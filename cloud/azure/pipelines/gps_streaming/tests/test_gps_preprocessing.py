from datetime import datetime, timedelta, timezone
import unittest

from cloud.azure.pipelines.gps_streaming.gps_preprocessing import (
    GpsFirstLayerRuntime,
    GpsObservation,
    GpsTransitionProcessor,
)
from cloud.azure.pipelines.gps_streaming.mock_detector import (
    MockDetectorConfig,
    MockFirstLayerDetector,
)
from cloud.azure.pipelines.gps_streaming.pipeline import MockFirstLayerPipeline


UTC = timezone.utc
START = datetime(2026, 9, 15, tzinfo=UTC)


def observation(
    sequence: int,
    *,
    seconds: float | None = None,
    lat: float = 37.5,
    lon: float = 127.0,
    raw_speed: float | None = 3.25,
) -> GpsObservation:
    event_time = START + timedelta(seconds=sequence if seconds is None else seconds)
    return GpsObservation(
        schema_version="canopy.gps.collector.v0.1",
        event_id=f"event-{sequence}",
        user_id="user-1",
        device_id="device-1",
        trip_id="trip-1",
        sequence=sequence,
        event_time=event_time,
        received_at=event_time,
        lat=lat,
        lon=lon,
        accuracy=5.0,
        speed=raw_speed,
        altitude_m=None,
        vertical_accuracy=None,
    )


class GpsObservationTest(unittest.TestCase):
    def test_parses_intended_payload_and_preserves_raw_speed(self) -> None:
        parsed = GpsObservation.from_payload(
            {
                "schema_version": "canopy.gps.collector.v0.1",
                "event_id": "event-1",
                "user_id": "user-1",
                "device_id": "device-1",
                "trip_id": "trip-1",
                "sequence": 1,
                "event_time": "2026-09-15T00:00:01Z",
                "received_at": "2026-09-15T00:00:02Z",
                "lat": 37.5,
                "lon": 127.0,
                "accuracy": 5.0,
                "speed": 3.25,
                "altitude_m": 20.0,
                "vertical_accuracy": 2.0,
            }
        )
        self.assertEqual(parsed.speed, 3.25)
        self.assertEqual(parsed.event_time.tzinfo, UTC)


class GpsTransitionProcessorTest(unittest.TestCase):
    def test_accepts_irregular_positive_dt_and_uses_actual_interval(self) -> None:
        processor = GpsTransitionProcessor()
        processor.process(observation(0, seconds=0.0, lat=0.0, lon=0.0))
        result = processor.process(observation(1, seconds=2.0, lat=0.0001, lon=0.0))

        self.assertTrue(result.transition_valid)
        self.assertEqual(result.dt_s, 2.0)
        self.assertAlmostEqual(result.distance_m, 11.1195, places=3)
        self.assertAlmostEqual(result.derived_speed_kmh, 20.0151, places=3)

    def test_rejects_above_200_without_clipping(self) -> None:
        processor = GpsTransitionProcessor()
        processor.process(observation(0, lat=0.0, lon=0.0))
        result = processor.process(observation(1, lat=0.01, lon=0.0))

        self.assertFalse(result.transition_valid)
        self.assertEqual(result.invalid_reason, "speed_above_200_kmh")
        self.assertIsNone(result.derived_speed_kmh)

    def test_late_event_does_not_move_the_trip_cursor_backwards(self) -> None:
        processor = GpsTransitionProcessor()
        processor.process(observation(10, seconds=10.0, lat=0.0, lon=0.0))
        late = processor.process(observation(5, seconds=5.0, lat=0.0, lon=0.0))
        current = processor.process(observation(11, seconds=11.0, lat=0.00001, lon=0.0))

        self.assertEqual(late.invalid_reason, "non_positive_dt")
        self.assertEqual(current.dt_s, 1.0)
        self.assertEqual(current.previous_event_time, START + timedelta(seconds=10))


class GpsFirstLayerRuntimeTest(unittest.TestCase):
    def test_251_observations_produce_one_250_speed_segment(self) -> None:
        detector = MockFirstLayerDetector(
            MockDetectorConfig(min_speed_points=250, max_speed_points=250)
        )
        runtime = GpsFirstLayerRuntime(
            first_layer=MockFirstLayerPipeline(detector=detector)
        )
        segments = []
        for sequence in range(251):
            output = runtime.process(
                observation(sequence, lat=37.5 + sequence * 0.00001)
            )
            if output.segment is not None:
                segments.append(output.segment)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].speed_point_count, 250)

    def test_invalid_transition_discards_partial_segment_state(self) -> None:
        detector = MockFirstLayerDetector(
            MockDetectorConfig(min_speed_points=250, max_speed_points=250)
        )
        runtime = GpsFirstLayerRuntime(
            first_layer=MockFirstLayerPipeline(detector=detector)
        )
        for sequence in range(51):
            runtime.process(observation(sequence, lat=sequence * 0.00001, lon=0.0))

        output = runtime.process(observation(51, lat=1.0, lon=0.0))
        self.assertEqual(output.point.invalid_reason, "speed_above_200_kmh")
        self.assertEqual(output.discarded_partial_speed_points, 50)
        self.assertEqual(detector.pending_speed_points("trip-1"), 0)


if __name__ == "__main__":
    unittest.main()

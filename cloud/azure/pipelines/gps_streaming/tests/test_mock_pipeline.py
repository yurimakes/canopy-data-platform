from datetime import datetime, timedelta, timezone
import unittest

from cloud.azure.pipelines.gps_streaming.features import RollingSpeedMin
from cloud.azure.pipelines.gps_streaming.mock_detector import (
    DetectorPoint,
    MockDetectorConfig,
    MockFirstLayerDetector,
)
from cloud.azure.pipelines.gps_streaming.pipeline import MockFirstLayerPipeline


UTC = timezone.utc


class RollingSpeedMinTest(unittest.TestCase):
    def test_retains_only_open_left_60_second_window(self) -> None:
        feature = RollingSpeedMin()
        start = datetime(2026, 9, 15, tzinfo=UTC)

        self.assertEqual(feature.update("trip", start, 1.0), 1.0)
        self.assertEqual(feature.update("trip", start + timedelta(seconds=59), 5.0), 1.0)
        self.assertEqual(feature.update("trip", start + timedelta(seconds=60), 4.0), 4.0)

    def test_rejects_out_of_order_events(self) -> None:
        feature = RollingSpeedMin()
        now = datetime(2026, 9, 15, tzinfo=UTC)
        feature.update("trip", now, 10.0)
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            feature.update("trip", now - timedelta(seconds=1), 9.0)


class MockDetectorTest(unittest.TestCase):
    def test_every_emitted_segment_has_200_to_300_speed_points(self) -> None:
        pipeline = MockFirstLayerPipeline()
        start = datetime(2026, 9, 15, tzinfo=UTC)
        segments = []

        for offset in range(2_000):
            enriched, segment = pipeline.process(
                trip_id="trip-1",
                user_id="user-1",
                event_time=start + timedelta(seconds=offset),
                derived_speed_kmh=float(offset % 80),
            )
            self.assertGreaterEqual(enriched.speed_min_60s, 0.0)
            if segment is not None:
                segments.append(segment)

        self.assertGreater(len(segments), 5)
        self.assertTrue(all(200 <= item.speed_point_count <= 300 for item in segments))
        self.assertTrue(all(item.status == "closed" for item in segments))

    def test_speed_min_placeholder_does_not_change_mock_output(self) -> None:
        config = MockDetectorConfig(seed=7)
        left = MockFirstLayerDetector(config)
        right = MockFirstLayerDetector(config)
        start = datetime(2026, 9, 15, tzinfo=UTC)
        left_events = []
        right_events = []

        for offset in range(1_000):
            common = {
                "trip_id": "trip-1",
                "user_id": "user-1",
                "event_time": start + timedelta(seconds=offset),
            }
            a = left.process(DetectorPoint(speed_min_60s=0.0, **common))
            b = right.process(DetectorPoint(speed_min_60s=199.0, **common))
            if a is not None:
                left_events.append(a)
            if b is not None:
                right_events.append(b)

        self.assertEqual(left_events, right_events)

    def test_partial_tail_is_not_emitted(self) -> None:
        detector = MockFirstLayerDetector(MockDetectorConfig(seed=11))
        start = datetime(2026, 9, 15, tzinfo=UTC)
        for offset in range(199):
            event = detector.process(
                DetectorPoint(
                    trip_id="short-trip",
                    user_id="user-1",
                    event_time=start + timedelta(seconds=offset),
                    speed_min_60s=1.0,
                )
            )
            self.assertIsNone(event)

        self.assertEqual(detector.clear_trip("short-trip"), 199)


if __name__ == "__main__":
    unittest.main()

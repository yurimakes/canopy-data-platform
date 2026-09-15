import json
import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertEqual(
            feature.update("trip", start + timedelta(seconds=59), 5.0), 1.0
        )
        self.assertEqual(
            feature.update("trip", start + timedelta(seconds=60), 4.0), 4.0
        )

    def test_rejects_out_of_order_events(self) -> None:
        feature = RollingSpeedMin()
        now = datetime(2026, 9, 15, tzinfo=UTC)
        feature.update("trip", now, 10.0)
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            feature.update("trip", now - timedelta(seconds=1), 9.0)


class MockDetectorTest(unittest.TestCase):
    def test_every_emitted_segment_has_250_to_300_speed_points(self) -> None:
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
        self.assertTrue(all(250 <= item.speed_point_count <= 300 for item in segments))
        self.assertTrue(all(item.status == "closed" for item in segments))

    def test_generated_targets_cannot_be_below_250(self) -> None:
        detector = MockFirstLayerDetector(MockDetectorConfig(seed=23))
        start = datetime(2026, 9, 15, tzinfo=UTC)

        for trip_number in range(500):
            trip_id = f"trip-{trip_number}"
            detector.process(DetectorPoint(trip_id, "user-1", start, speed_min_60s=1.0))
            snapshot = detector.snapshot_trip(trip_id)
            self.assertIsNotNone(snapshot)
            self.assertGreaterEqual(snapshot["target_points"], 250)
            self.assertLessEqual(snapshot["target_points"], 300)

        with self.assertRaisesRegex(ValueError, "at least 250"):
            MockDetectorConfig(min_speed_points=249)

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

    def test_json_state_restoration_preserves_target_count_and_rng(self) -> None:
        config = MockDetectorConfig(seed=17)
        left = MockFirstLayerDetector(config)
        right = MockFirstLayerDetector(config)
        start = datetime(2026, 9, 15, tzinfo=UTC)

        for offset in range(137):
            left.process(
                DetectorPoint(
                    "trip-1", "user-1", start + timedelta(seconds=offset), 1.0
                )
            )

        snapshot = json.loads(json.dumps(left.snapshot_trip("trip-1")))
        self.assertGreaterEqual(snapshot["target_points"], 250)
        self.assertEqual(snapshot["point_count"], 137)
        right.restore_trip("trip-1", snapshot)

        left_events = []
        right_events = []
        for offset in range(137, 1_000):
            point = DetectorPoint(
                "trip-1", "user-1", start + timedelta(seconds=offset), 1.0
            )
            left_event = left.process(point)
            right_event = right.process(point)
            if left_event is not None:
                left_events.append(left_event)
            if right_event is not None:
                right_events.append(right_event)

        self.assertEqual(left_events, right_events)

    def test_restore_rejects_target_from_old_contract(self) -> None:
        detector = MockFirstLayerDetector()
        start = datetime(2026, 9, 15, tzinfo=UTC)
        detector.process(DetectorPoint("trip-1", "user-1", start, 1.0))
        snapshot = detector.snapshot_trip("trip-1")
        snapshot["target_points"] = 249

        with self.assertRaisesRegex(ValueError, "incompatible"):
            detector.restore_trip("trip-1", snapshot)

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

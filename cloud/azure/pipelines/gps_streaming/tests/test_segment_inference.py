from datetime import datetime, timezone
import unittest

import pandas as pd

from cloud.azure.pipelines.gps_streaming.mock_detector import SegmentEvent
from cloud.azure.pipelines.gps_streaming.segment_inference import infer_closed_segment
from cloud.azure.pipelines.gps_streaming.windowing import (
    build_speed_windows,
    representative_start_indices,
)


UTC = timezone.utc


def _segment(speed_point_count: int) -> SegmentEvent:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    return SegmentEvent(
        trip_id="trip-1",
        user_id="user-1",
        segment_id="trip-1:mock:0001",
        start_time=now,
        end_time=now,
        speed_point_count=speed_point_count,
        weak_mode="walk",
        weak_confidence=0.61,
        status="closed",
        detector_version="mock-random-v1",
    )


class FakePyfuncModel:
    def __init__(self) -> None:
        self.received = None

    def predict(self, model_input):
        self.received = model_input
        rows = len(model_input)
        probabilities = (
            [[0.05, 0.70, 0.20, 0.03, 0.02]]
            if rows == 1
            else [
                [0.05, 0.70, 0.20, 0.03, 0.02],
                [0.05, 0.20, 0.70, 0.03, 0.02],
                [0.05, 0.60, 0.30, 0.03, 0.02],
            ]
        )
        return pd.DataFrame(
            {
                "predicted_class": ["bus"] * rows,
                "confidence": [max(row) for row in probabilities],
                "probabilities": probabilities,
            }
        )


class WindowingTest(unittest.TestCase):
    def test_even_starts_include_both_segment_ends(self) -> None:
        self.assertEqual(representative_start_indices(400, 5), (0, 50, 100, 150, 200))
        self.assertEqual(representative_start_indices(662, 7), (0, 77, 154, 231, 308, 385, 462))

    def test_mock_sized_segment_uses_expected_policy(self) -> None:
        self.assertEqual(len(build_speed_windows([10.0] * 200)), 1)
        self.assertEqual(len(build_speed_windows([10.0] * 249)), 1)
        self.assertEqual(len(build_speed_windows([10.0] * 250)), 3)
        self.assertEqual(len(build_speed_windows([10.0] * 300)), 3)


class SegmentInferenceTest(unittest.TestCase):
    def test_builds_exact_pyfunc_batch_and_aggregates_probabilities(self) -> None:
        model = FakePyfuncModel()
        result = infer_closed_segment(_segment(250), [10.0] * 250, model)

        self.assertEqual(list(model.received.columns), ["speed_sequence"])
        self.assertEqual(model.received.shape, (3, 1))
        self.assertTrue(all(len(row) == 200 for row in model.received["speed_sequence"]))
        self.assertEqual(result.status, "scored")
        self.assertEqual(result.strong_mode, "bus")
        self.assertEqual(result.window_count, 3)
        self.assertAlmostEqual(result.probabilities[1], 0.5)
        self.assertEqual(result.weak_mode, "walk")

    def test_insufficient_history_is_retryable_and_does_not_call_model(self) -> None:
        model = FakePyfuncModel()
        result = infer_closed_segment(_segment(199), [10.0] * 199, model)

        self.assertEqual(result.status, "insufficient_history")
        self.assertIsNone(result.strong_mode)
        self.assertEqual(result.window_count, 0)
        self.assertIsNone(model.received)


if __name__ == "__main__":
    unittest.main()

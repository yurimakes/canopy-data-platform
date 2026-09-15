from datetime import datetime, timezone
import unittest

from cloud.azure.pipelines.gps_streaming.databricks_adapter import (
    DatabricksInferenceConfig,
    prediction_row,
)
from cloud.azure.pipelines.gps_streaming.segment_inference import SegmentInferenceResult


UTC = timezone.utc


class DatabricksInferenceConfigTest(unittest.TestCase):
    def test_requires_only_workspace_specific_runtime_values(self) -> None:
        config = DatabricksInferenceConfig(
            model_uri="models:/canopy_speedtransformer@champion",
            checkpoint_location="abfss://checkpoints/segment-inference",
        )
        self.assertEqual(config.gps_features_table, "canopy.silver.gps_features")
        self.assertEqual(config.predictions_table, "canopy.gold.mode_segment_predictions")

    def test_rejects_unsafe_or_incomplete_table_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "catalog.schema.table"):
            DatabricksInferenceConfig(
                model_uri="model",
                checkpoint_location="checkpoint",
                predictions_table="gold.predictions",
            )


class PredictionRowTest(unittest.TestCase):
    def test_maps_domain_status_and_runtime_metadata(self) -> None:
        now = datetime(2026, 9, 15, tzinfo=UTC)
        result = SegmentInferenceResult(
            trip_id="trip-1",
            user_id="user-1",
            segment_id="segment-1",
            start_time=now,
            end_time=now,
            weak_mode="walk",
            weak_confidence=0.6,
            detector_version="mock-random-v1",
            status="scored",
            strong_mode="bus",
            strong_confidence=0.7,
            probabilities=(0.1, 0.7, 0.1, 0.05, 0.05),
            window_count=3,
            speed_point_count=250,
        )

        row = prediction_row(
            result,
            model_uri="models:/canopy_speedtransformer@champion",
            batch_id=42,
            processed_at=now,
        )
        self.assertNotIn("status", row)
        self.assertEqual(row["inference_status"], "scored")
        self.assertEqual(row["stream_batch_id"], 42)
        self.assertEqual(row["probabilities"], [0.1, 0.7, 0.1, 0.05, 0.05])


if __name__ == "__main__":
    unittest.main()

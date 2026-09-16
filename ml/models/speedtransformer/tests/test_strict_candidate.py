"""Contract and local artifact checks for the strict candidate."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import mlflow.pyfunc
import numpy as np
import pandas as pd
import torch

from cloud.azure.pipelines.gps_streaming.mock_detector import SegmentEvent
from cloud.azure.pipelines.gps_streaming.segment_inference import infer_closed_segment
from ml.models.speedtransformer.inference.log_strict_candidate import (
    MODEL_CODE,
    extract_verified_artifact,
)
from ml.models.speedtransformer.inference.strict_pyfunc import StrictSpeedTransformer


class FixedLogits:
    def __init__(self) -> None:
        self.received = None

    def __call__(self, values):
        self.received = values
        return torch.tensor([[5.0, 1.0, 2.0, 3.0, 4.0]]).repeat(len(values), 1)


class StrictCandidateContractTest(unittest.TestCase):
    def test_rejects_invalid_speed_sequences(self) -> None:
        invalid_sequences = (
            [1.0] * 199, [1.0] * 201, [float("nan")] * 200,
            [-1.0] * 200, [201.0] * 200,
        )
        for invalid in invalid_sequences:
            with self.subTest(invalid=invalid[:1], length=len(invalid)):
                with self.assertRaises(ValueError):
                    StrictSpeedTransformer._sequences(pd.DataFrame({"speed_sequence": [invalid]}))

    def test_json_scaling_and_service_probability_order(self) -> None:
        model = StrictSpeedTransformer()
        model.mean = 10.0
        model.scale = 2.0
        model.model = FixedLogits()

        output = model.predict(None, pd.DataFrame({"speed_sequence": [[12.0] * 200]}))

        np.testing.assert_allclose(model.model.received.numpy(), np.ones((1, 200, 1)))
        self.assertEqual(output.loc[0, "predicted_class"], "walk")
        self.assertEqual(len(output.loc[0, "probabilities"]), 5)
        self.assertAlmostEqual(sum(output.loc[0, "probabilities"]), 1.0)
        expected = torch.softmax(torch.tensor([5.0, 1.0, 2.0, 3.0, 4.0]), dim=0).numpy()
        np.testing.assert_allclose(output.loc[0, "probabilities"], expected[[1, 3, 2, 4, 0]])
        self.assertEqual(int(np.argmax(output.loc[0, "probabilities"])), 4)
        self.assertAlmostEqual(output.loc[0, "confidence"], output.loc[0, "probabilities"][4])

    def test_subway_maps_to_train(self) -> None:
        model = StrictSpeedTransformer()
        model.mean = 0.0
        model.scale = 1.0
        model.model = lambda values: torch.tensor(
            [[0.0, 1.0, 2.0, 3.0, 9.0]]
        ).repeat(len(values), 1)
        output = model.predict(None, pd.DataFrame({"speed_sequence": [[10.0] * 200]}))
        self.assertEqual(output.loc[0, "predicted_class"], "train")
        self.assertEqual(int(np.argmax(output.loc[0, "probabilities"])), 3)


class StrictCandidateArtifactTest(unittest.TestCase):
    def test_mlflow_load_and_existing_segment_adapter(self) -> None:
        archive = os.environ.get("CANOPY_STRICT_ARTIFACT_ZIP")
        if not archive:
            self.skipTest("set CANOPY_STRICT_ARTIFACT_ZIP for the real checkpoint smoke test")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact_dir = root / "artifact"
            artifact_dir.mkdir()
            extract_verified_artifact(Path(archive), artifact_dir)
            model_dir = root / "mlflow_model"
            mlflow.pyfunc.save_model(
                path=str(model_dir),
                python_model=str(
                    Path(__file__).resolve().parents[1] / "inference" / "strict_pyfunc.py"
                ),
                code_paths=[str(MODEL_CODE)],
                artifacts={name: str(artifact_dir / filename) for name, filename in (
                    ("checkpoint", "model.pt"),
                    ("scaler", "scaler.json"),
                    ("manifest", "manifest.json"),
                )},
                pip_requirements=[
                    "mlflow>=3,<4", "numpy>=2.1,<3", "pandas>=2.2,<3", "torch>=2.11,<2.12"
                ],
            )
            model = mlflow.pyfunc.load_model(str(model_dir))
            direct = model.predict(pd.DataFrame({"speed_sequence": [[10.0] * 200]}))
            self.assertEqual(len(direct.loc[0, "probabilities"]), 5)
            self.assertAlmostEqual(sum(direct.loc[0, "probabilities"]), 1.0, places=5)

            now = datetime(2026, 9, 16, tzinfo=timezone.utc)
            segment = SegmentEvent(
                "trip", "user", "segment", now, now, 250,
                "walk", 0.6, "closed", "mock-random-v2",
            )
            result = infer_closed_segment(segment, [10.0] * 250, model)
            self.assertEqual(result.status, "scored")
            self.assertEqual(result.window_count, 3)
            self.assertEqual(result.strong_mode, direct.loc[0, "predicted_class"])


if __name__ == "__main__":
    unittest.main()

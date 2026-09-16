"""MLflow boundary for the strict SpeedTransformer candidate artifact."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
import torch

# MLflow adds code_paths to sys.path. The fallback supports local repository tests.
_LOCAL_CODE = Path(__file__).resolve().parents[1] / "artifacts" / "playground_v1" / "code"
if _LOCAL_CODE.is_dir():
    sys.path.insert(0, str(_LOCAL_CODE))
from model_utils import TrajectoryTransformer


SEQUENCE_LENGTH = 200
MAX_SPEED_KMH = 200.0
SERVICE_CLASSES = ("bike", "bus", "car", "train", "walk")
SERVICE_ORDER = (1, 3, 2, 4, 0)
ARTIFACT_VERSION = "speedtransformer-strict-large-seed316-v1"
LABEL_MAPPING = {"0": "WALK", "1": "BIKE", "2": "CAR", "3": "BUS", "4": "SUBWAY"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class StrictSpeedTransformer(mlflow.pyfunc.PythonModel):
    """Accept only 200 physical speeds; return Canopy service class order."""

    def load_context(self, context) -> None:
        checkpoint = Path(context.artifacts["checkpoint"])
        scaler_path = Path(context.artifacts["scaler"])
        manifest = json.loads(Path(context.artifacts["manifest"]).read_text(encoding="utf-8"))
        scaler = json.loads(scaler_path.read_text(encoding="utf-8"))

        if manifest.get("artifact_version") != ARTIFACT_VERSION:
            raise ValueError("unexpected strict SpeedTransformer artifact version")
        if manifest.get("label_mapping") != LABEL_MAPPING:
            raise ValueError("unexpected strict SpeedTransformer label mapping")
        if _sha256(checkpoint) != manifest.get("model_sha256", "").upper():
            raise ValueError("checkpoint SHA256 does not match manifest")
        if _sha256(scaler_path) != manifest.get("scaler_sha256", "").upper():
            raise ValueError("scaler SHA256 does not match manifest")
        if (
            scaler.get("format") != "sklearn_standard_scaler_json_v1"
            or scaler.get("feature_names") != ["speed_kmh"]
        ):
            raise ValueError("unexpected strict SpeedTransformer scaler contract")
        if (
            scaler.get("n_features_in") != 1
            or scaler.get("with_mean") is not True
            or scaler.get("with_std") is not True
        ):
            raise ValueError("strict SpeedTransformer requires a one-feature standard scaler")
        self.mean = float(scaler["mean"][0])
        self.scale = float(scaler["scale"][0])
        if not math.isfinite(self.mean) or not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("invalid strict SpeedTransformer scaler values")

        hp = manifest["hyperparameters"]
        if (
            hp["feature_size"] != 1
            or hp["num_classes"] != len(SERVICE_CLASSES)
            or hp["window_size"] != SEQUENCE_LENGTH
        ):
            raise ValueError("strict SpeedTransformer architecture violates input contract")
        self.model = TrajectoryTransformer(
            feature_size=hp["feature_size"],
            num_classes=hp["num_classes"],
            d_model=hp["d_model"],
            nhead=hp["nhead"],
            kv_heads=hp["kv_heads"],
            num_layers=hp["num_layers"],
            window_size=hp["window_size"],
            dropout=hp["dropout"],
        )
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()

    @staticmethod
    def _sequences(model_input: pd.DataFrame) -> np.ndarray:
        if (
            not isinstance(model_input, pd.DataFrame)
            or list(model_input.columns) != ["speed_sequence"]
        ):
            raise ValueError("input must be a DataFrame with only speed_sequence")
        rows = []
        for index, value in model_input["speed_sequence"].items():
            sequence = np.asarray(value, dtype=np.float64)
            if sequence.ndim != 1 or len(sequence) != SEQUENCE_LENGTH:
                raise ValueError(f"row {index}: speed_sequence must contain exactly 200 values")
            if (
                not np.isfinite(sequence).all()
                or (sequence < 0).any()
                or (sequence > MAX_SPEED_KMH).any()
            ):
                raise ValueError(f"row {index}: speeds must be finite and within [0, 200] km/h")
            rows.append(sequence)
        return np.stack(rows) if rows else np.empty((0, SEQUENCE_LENGTH), dtype=np.float64)

    @torch.no_grad()
    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        speeds = self._sequences(model_input)
        if len(speeds) == 0:
            return pd.DataFrame(columns=["predicted_class", "confidence", "probabilities"])
        standardized = ((speeds - self.mean) / self.scale).astype(np.float32)
        logits = self.model(torch.from_numpy(standardized[..., None]))
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()[:, SERVICE_ORDER]
        indices = probabilities.argmax(axis=1)
        return pd.DataFrame(
            {
                "predicted_class": [SERVICE_CLASSES[index] for index in indices],
                "confidence": probabilities[np.arange(len(indices)), indices].astype(float),
                "probabilities": [row.astype(float).tolist() for row in probabilities],
            }
        )


mlflow.models.set_model(StrictSpeedTransformer())

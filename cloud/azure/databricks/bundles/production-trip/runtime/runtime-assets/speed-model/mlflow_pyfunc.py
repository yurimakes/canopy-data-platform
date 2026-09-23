from __future__ import annotations

import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import joblib
import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
import torch

from model_utils import TrajectoryTransformer


SEQUENCE_LENGTH = 200
FEATURE_COLUMN = "speed_sequence"
SCALER_FEATURE_COLUMN = "speed"
MAX_SPEED_KMH = 200.0


class SpeedTransformerPyfuncModel(mlflow.pyfunc.PythonModel):
    """MLflow pyfunc wrapper for the verified AI Hub speed-only champion."""

    def load_context(self, context):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.scaler = joblib.load(context.artifacts["scaler"])
        self.label_encoder = joblib.load(context.artifacts["label_encoder"])

        self.model = TrajectoryTransformer(
            feature_size=1,
            num_classes=len(self.label_encoder.classes_),
            d_model=128,
            nhead=8,
            kv_heads=4,
            num_layers=4,
            window_size=SEQUENCE_LENGTH,
            dropout=0.1,
        ).to(self.device)

        state = torch.load(
            Path(context.artifacts["checkpoint"]),
            map_location=self.device,
        )
        if any(key.startswith("module.") for key in state):
            state = {key.removeprefix("module."): value for key, value in state.items()}
        self.model.load_state_dict(state, strict=True)
        self.model.eval()

    @staticmethod
    def _coerce_sequences(model_input: pd.DataFrame) -> np.ndarray:
        if not isinstance(model_input, pd.DataFrame):
            raise TypeError("model_input must be a pandas DataFrame")
        if FEATURE_COLUMN not in model_input.columns:
            raise ValueError(f"missing required column: {FEATURE_COLUMN}")

        rows = []
        for index, value in model_input[FEATURE_COLUMN].items():
            sequence = np.asarray(value, dtype=np.float64)
            if sequence.ndim != 1 or sequence.shape[0] != SEQUENCE_LENGTH:
                raise ValueError(
                    f"row {index}: {FEATURE_COLUMN} must contain exactly "
                    f"{SEQUENCE_LENGTH} speed values"
                )
            if not np.isfinite(sequence).all():
                raise ValueError(f"row {index}: speed sequence contains non-finite values")
            if (sequence < 0.0).any():
                raise ValueError(f"row {index}: speed must be >= 0 km/h")
            if (sequence > MAX_SPEED_KMH).any():
                raise ValueError(
                    f"row {index}: speed above {MAX_SPEED_KMH} km/h is outside "
                    "the champion input contract"
                )
            rows.append(sequence)

        if not rows:
            return np.empty((0, SEQUENCE_LENGTH), dtype=np.float64)
        return np.stack(rows, axis=0)

    @torch.no_grad()
    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        raw = self._coerce_sequences(model_input)
        if raw.shape[0] == 0:
            return pd.DataFrame(
                columns=["predicted_class", "confidence", "probabilities"]
            )

        scaler_input = pd.DataFrame(
            raw.reshape(-1, 1),
            columns=[SCALER_FEATURE_COLUMN],
        )
        standardized = self.scaler.transform(scaler_input).reshape(
            raw.shape[0], SEQUENCE_LENGTH, 1
        )
        tensor = torch.from_numpy(standardized.astype(np.float32)).to(self.device)

        logits = self.model(tensor)
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        indices = probabilities.argmax(axis=1)
        classes = self.label_encoder.inverse_transform(indices)
        confidence = probabilities[np.arange(len(indices)), indices]

        return pd.DataFrame(
            {
                "predicted_class": classes.astype(str),
                "confidence": confidence.astype(float),
                "probabilities": [row.astype(float).tolist() for row in probabilities],
            }
        )


mlflow.models.set_model(SpeedTransformerPyfuncModel())

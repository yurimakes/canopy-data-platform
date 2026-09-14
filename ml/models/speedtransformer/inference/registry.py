from __future__ import annotations

import os
from functools import lru_cache

import mlflow
import mlflow.pyfunc
import pandas as pd


MODEL_URI_ENV = "CANOPY_SPEEDTRANSFORMER_MODEL_URI"
REGISTRY_URI = "databricks-uc"
INPUT_COLUMN = "speed_sequence"
SEQUENCE_LENGTH = 200


@lru_cache(maxsize=4)
def load_model(model_uri: str | None = None):
    """Load the registered MLflow pyfunc once per process."""
    uri = model_uri or os.getenv(MODEL_URI_ENV)
    if not uri:
        raise RuntimeError(
            f"SpeedTransformer model URI is required. Pass model_uri or set {MODEL_URI_ENV}."
        )

    mlflow.set_registry_uri(REGISTRY_URI)
    return mlflow.pyfunc.load_model(uri)


def predict_speed_sequences(
    speed_sequences: list[list[float]],
    model_uri: str | None = None,
) -> pd.DataFrame:
    """Invoke the registered champion using Canopy's stable runtime schema."""
    for index, sequence in enumerate(speed_sequences):
        if len(sequence) != SEQUENCE_LENGTH:
            raise ValueError(
                f"sequence {index} must contain exactly {SEQUENCE_LENGTH} speed values"
            )

    frame = pd.DataFrame({INPUT_COLUMN: speed_sequences})
    return load_model(model_uri).predict(frame)

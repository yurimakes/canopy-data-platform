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
    """프로세스당 한 번만 등록된 MLflow pyfunc 모델을 로드합니다."""
    uri = model_uri or os.getenv(MODEL_URI_ENV)
    if not uri:
        raise RuntimeError(
            f"SpeedTransformer model URI가 필요합니다. model_uri를 전달하거나 "
            f"{MODEL_URI_ENV} 환경변수를 설정하세요."
        )

    mlflow.set_registry_uri(REGISTRY_URI)
    return mlflow.pyfunc.load_model(uri)


def predict_speed_sequences(
    speed_sequences: list[list[float]],
    model_uri: str | None = None,
) -> pd.DataFrame:
    """Canopy의 고정 런타임 스키마로 등록된 champion 모델을 호출합니다."""
    for index, sequence in enumerate(speed_sequences):
        if len(sequence) != SEQUENCE_LENGTH:
            raise ValueError(
                f"sequence {index}는 정확히 {SEQUENCE_LENGTH}개의 speed 값을 가져야 합니다."
            )

    frame = pd.DataFrame({INPUT_COLUMN: speed_sequences})
    return load_model(model_uri).predict(frame)

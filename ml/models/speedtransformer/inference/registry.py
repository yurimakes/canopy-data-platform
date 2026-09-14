from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import mlflow.pyfunc
import pandas as pd


MODEL_URI_ENV = "CANOPY_SPEEDTRANSFORMER_MODEL_URI"
LOCAL_MODEL_ENV = "CANOPY_SPEEDTRANSFORMER_LOCAL_MODEL"
INPUT_COLUMN = "speed_sequence"
SEQUENCE_LENGTH = 200
DEFAULT_LOCAL_MODEL = (
    Path(__file__).resolve().parents[1] / "artifacts" / "playground_v1"
)


@lru_cache(maxsize=4)
def load_model(
    model_path: str | Path | None = None,
    model_uri: str | None = None,
):
    """로컬 MLflow artifact를 우선 사용하고, 필요할 때만 원격 URI를 사용합니다."""
    if model_path is not None and model_uri is not None:
        raise ValueError("model_path와 model_uri는 동시에 지정할 수 없습니다.")

    if model_path is not None:
        return mlflow.pyfunc.load_model(str(Path(model_path).expanduser().resolve()))

    if model_uri is not None:
        return mlflow.pyfunc.load_model(model_uri)

    configured_local = os.getenv(LOCAL_MODEL_ENV)
    if configured_local:
        return mlflow.pyfunc.load_model(
            str(Path(configured_local).expanduser().resolve())
        )

    if DEFAULT_LOCAL_MODEL.exists():
        return mlflow.pyfunc.load_model(str(DEFAULT_LOCAL_MODEL))

    configured_uri = os.getenv(MODEL_URI_ENV)
    if configured_uri:
        return mlflow.pyfunc.load_model(configured_uri)

    raise RuntimeError(
        "SpeedTransformer 모델을 찾을 수 없습니다. "
        f"기본 로컬 경로({DEFAULT_LOCAL_MODEL})에 playground artifact를 두거나, "
        f"{LOCAL_MODEL_ENV} 또는 {MODEL_URI_ENV}를 설정하세요."
    )


def predict_speed_sequences(
    speed_sequences: list[list[float]],
    model_path: str | Path | None = None,
    model_uri: str | None = None,
) -> pd.DataFrame:
    """Canopy의 고정 런타임 스키마로 SpeedTransformer를 호출합니다."""
    for index, sequence in enumerate(speed_sequences):
        if len(sequence) != SEQUENCE_LENGTH:
            raise ValueError(
                f"sequence {index}는 정확히 {SEQUENCE_LENGTH}개의 speed 값을 가져야 합니다."
            )

    frame = pd.DataFrame({INPUT_COLUMN: speed_sequences})
    return load_model(model_path=model_path, model_uri=model_uri).predict(frame)

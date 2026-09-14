#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlflow.pyfunc
import pandas as pd

INPUT_COLUMN = "speed_sequence"
SEQUENCE_LENGTH = 200
DEFAULT_LOCAL_MODEL = Path(__file__).resolve().parents[1] / "artifacts" / "playground_v1"


def load_input(path: Path) -> list[float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sequence = payload.get(INPUT_COLUMN)
    if not isinstance(sequence, list):
        raise ValueError(f"입력 JSON에는 `{INPUT_COLUMN}` 배열이 필요합니다.")
    if len(sequence) != SEQUENCE_LENGTH:
        raise ValueError(f"`{INPUT_COLUMN}` 길이는 정확히 {SEQUENCE_LENGTH}이어야 합니다.")
    return [float(value) for value in sequence]


def main() -> None:
    parser = argparse.ArgumentParser(description="SpeedTransformer 로컬/MLflow 추론 CLI")
    parser.add_argument("--input", type=Path, required=True, help="speed_sequence JSON 경로")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=DEFAULT_LOCAL_MODEL,
        help="로컬 MLflow 모델 디렉터리. 기본값: artifacts/playground_v1",
    )
    parser.add_argument(
        "--model-uri",
        default=None,
        help="선택 사항: MLflow Registry model URI. 지정하면 --model-path보다 우선합니다.",
    )
    args = parser.parse_args()

    sequence = load_input(args.input)
    source = args.model_uri or str(args.model_path)

    if args.model_uri is None and not args.model_path.exists():
        raise FileNotFoundError(
            f"로컬 모델을 찾을 수 없습니다: {args.model_path}\n"
            "playground artifact를 먼저 준비하거나 --model-uri를 지정하세요."
        )

    model = mlflow.pyfunc.load_model(source)
    result = model.predict(pd.DataFrame({INPUT_COLUMN: [sequence]}))
    print(result.to_json(orient="records", force_ascii=False, indent=2))


if __name__ == "__main__":
    main()

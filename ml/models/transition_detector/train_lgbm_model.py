"""Train and log the Canopy LightGBM transportation-mode classifier with MLflow.

This module preserves the upstream model logic while making training callable,
configurable, and suitable for Databricks Jobs / MLflow tracking.

Expected input files under --data-dir:
  - train_10000.parquet
  - val_3000.parquet

Required raw columns:
  trip_id, latitude, longitude, timestamp, mode

The logged MLflow model is the native pointwise LightGBM classifier. Trip-level
smoothing remains an explicit post-processing/evaluation step because it depends
on trajectory context rather than a single feature row.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_fscore_support,
)

from preprocessing import extract_advanced_features_v3


SEED = 42
FEATURES = [
    "speed",
    "acceleration",
    "distance",
    "bearing_change",
    "speed_mean_5",
    "speed_std_5",
    "speed_max_10",
    "speed_mean_30",
    "speed_std_30",
    "speed_max_60",
    "speed_mean_150",
    "stop_count_60",
    "stop_count_150",
    "stoppage_ratio_60",
    "speed_q25_60",
    "speed_q75_60",
    "accel_std_30",
]

ORIGINAL_MODE_NAMES = {
    0: "Walk",
    1: "Bike",
    2: "Car",
    3: "Bus",
    5: "Subway",
}
TRAIN_TO_COMPACT = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4}
COMPACT_TO_ORIGINAL = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5}
TARGET_NAMES = ["Walk", "Bike", "Car", "Bus", "Subway"]


DEFAULT_MODEL_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 8,
    "random_state": SEED,
    "n_jobs": -1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "./data"),
        help="Directory containing train_10000.parquet and val_3000.parquet.",
    )
    parser.add_argument("--train-file", default="train_10000.parquet")
    parser.add_argument("--val-file", default="val_3000.parquet")
    parser.add_argument("--train-trips", type=int, default=1000)
    parser.add_argument("--val-trips", type=int, default=200)
    parser.add_argument("--test-trips", type=int, default=200)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--chunk-size", type=int, default=300)
    parser.add_argument("--smoothing-window", type=int, default=21)
    parser.add_argument("--min-segment-len", type=int, default=10)
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "/Shared/canopy-transition-lgbm"),
    )
    parser.add_argument(
        "--run-name",
        default=os.getenv("MLFLOW_RUN_NAME", "transition-lgbm-train"),
    )
    parser.add_argument(
        "--registered-model-name",
        default=os.getenv("MLFLOW_REGISTERED_MODEL_NAME"),
        help="Optional Databricks/MLflow registered model name.",
    )
    return parser.parse_args()


def _apply_compact_labels(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["mode_compact"] = result["mode"].map(TRAIN_TO_COMPACT)
    if result["mode_compact"].isna().any():
        unexpected = sorted(result.loc[result["mode_compact"].isna(), "mode"].unique())
        raise ValueError(f"Unexpected mode labels: {unexpected}")
    result["mode_compact"] = result["mode_compact"].astype(int)
    return result


def load_and_split_data(
    data_dir: Path,
    train_file: str,
    val_file: str,
    train_trips: int,
    val_trips: int,
    test_trips: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_path = data_dir / train_file
    val_path = data_dir / val_file

    if not train_path.exists():
        raise FileNotFoundError(train_path)
    if not val_path.exists():
        raise FileNotFoundError(val_path)

    train_full = pd.read_parquet(train_path)
    val_full = pd.read_parquet(val_path)

    required = {"trip_id", "latitude", "longitude", "timestamp", "mode"}
    for name, frame in (("train", train_full), ("validation", val_full)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{name} dataset missing required columns: {missing}")

    rng = np.random.default_rng(seed)

    train_ids = np.array(train_full["trip_id"].dropna().unique(), copy=True)
    rng.shuffle(train_ids)
    train_ids = train_ids[:train_trips]

    candidate_ids = np.array(val_full["trip_id"].dropna().unique(), copy=True)
    rng.shuffle(candidate_ids)
    requested = val_trips + test_trips
    if len(candidate_ids) < requested:
        raise ValueError(
            f"Validation parquet contains {len(candidate_ids)} trips, "
            f"but {requested} are required for val+test."
        )

    selected = candidate_ids[:requested]
    val_ids = selected[:val_trips]
    test_ids = selected[val_trips:]

    train_df = train_full[train_full["trip_id"].isin(train_ids)].copy()
    val_df = val_full[val_full["trip_id"].isin(val_ids)].copy()
    test_df = val_full[val_full["trip_id"].isin(test_ids)].copy()

    return tuple(_apply_compact_labels(df) for df in (train_df, val_df, test_df))


def train_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    params: dict[str, Any] | None = None,
) -> lgb.LGBMClassifier:
    effective_params = {**DEFAULT_MODEL_PARAMS, **(params or {})}
    model = lgb.LGBMClassifier(**effective_params)
    model.fit(
        train_df[FEATURES],
        train_df["mode_compact"],
        eval_set=[(val_df[FEATURES], val_df["mode_compact"])],
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
    )
    return model


def apply_balanced_smoothing_to_test(
    df: pd.DataFrame,
    model: lgb.LGBMClassifier,
    *,
    chunk_size: int,
    window_size: int,
) -> pd.DataFrame:
    processed_chunks: list[pd.DataFrame] = []

    for _, group in df.groupby("trip_id", sort=False):
        group = group.reset_index(drop=True)
        for start_idx in range(0, len(group), chunk_size):
            chunk = group.iloc[start_idx : start_idx + chunk_size].copy()
            if len(chunk) < 5:
                continue

            chunk["pred_mode_compact"] = model.predict(chunk[FEATURES]).astype(int)
            chunk["smoothed_mode_compact"] = (
                chunk["pred_mode_compact"]
                .rolling(window=window_size, center=True, min_periods=1)
                .apply(lambda s: pd.Series(s).mode().iloc[0], raw=False)
                .astype(int)
            )
            processed_chunks.append(chunk)

    if not processed_chunks:
        raise ValueError("No test chunks were large enough for evaluation.")
    return pd.concat(processed_chunks, ignore_index=True)


def balanced_clean_segments_compact(
    df_subset: pd.DataFrame,
    *,
    mode_col: str = "smoothed_mode_compact",
    min_len: int = 10,
) -> np.ndarray:
    modes = df_subset[mode_col].to_numpy(copy=True)
    if len(modes) == 0:
        return modes

    changed = True
    iteration = 0
    while changed and iteration < 5:
        changed = False
        iteration += 1
        segments = []
        start = 0

        for idx in range(1, len(modes)):
            if modes[idx] != modes[start]:
                segments.append((start, idx - 1, modes[start]))
                start = idx
        segments.append((start, len(modes) - 1, modes[start]))

        for idx, (seg_start, seg_end, _) in enumerate(segments):
            length = seg_end - seg_start + 1
            if length >= min_len or len(segments) <= 1:
                continue

            if 0 < idx < len(segments) - 1:
                prev_len = segments[idx - 1][1] - segments[idx - 1][0] + 1
                next_len = segments[idx + 1][1] - segments[idx + 1][0] + 1
                target_mode = (
                    segments[idx - 1][2]
                    if prev_len >= next_len
                    else segments[idx + 1][2]
                )
            elif idx > 0:
                target_mode = segments[idx - 1][2]
            else:
                target_mode = segments[idx + 1][2]

            modes[seg_start : seg_end + 1] = target_mode
            changed = True
            break

    return modes


def evaluate_with_smoothing(
    test_df: pd.DataFrame,
    model: lgb.LGBMClassifier,
    *,
    chunk_size: int,
    smoothing_window: int,
    min_segment_len: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    scored = apply_balanced_smoothing_to_test(
        test_df,
        model,
        chunk_size=chunk_size,
        window_size=smoothing_window,
    )

    cleaned: list[int] = []
    for _, group in scored.groupby("trip_id", sort=False):
        cleaned.extend(
            balanced_clean_segments_compact(
                group.reset_index(drop=True),
                min_len=min_segment_len,
            ).tolist()
        )

    scored["super_cleaned_mode_compact"] = cleaned
    y_true = scored["mode_compact"].to_numpy()
    y_pred = scored["super_cleaned_mode_compact"].to_numpy()

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(range(len(TARGET_NAMES))),
        zero_division=0,
    )
    _, _, macro_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="macro",
        zero_division=0,
    )

    metrics: dict[str, float] = {
        "test_accuracy_smoothed": float(accuracy_score(y_true, y_pred)),
        "test_macro_f1_smoothed": float(macro_f1),
    }
    for idx, name in enumerate(TARGET_NAMES):
        key = name.lower()
        metrics[f"test_{key}_precision_smoothed"] = float(precision[idx])
        metrics[f"test_{key}_recall_smoothed"] = float(recall[idx])
        metrics[f"test_{key}_f1_smoothed"] = float(f1[idx])

    report = classification_report(
        y_true,
        y_pred,
        target_names=TARGET_NAMES,
        digits=4,
        zero_division=0,
        output_dict=True,
    )
    return metrics, report


def run_training(args: argparse.Namespace) -> str:
    data_dir = Path(args.data_dir).expanduser().resolve()
    mlflow.set_experiment(args.experiment_name)

    with mlflow.start_run(run_name=args.run_name) as run:
        mlflow.set_tags(
            {
                "canopy.model_role": "transportation_mode_classifier",
                "canopy.model_family": "lightgbm",
                "canopy.source": "riekim/canopy-transition-model",
                "canopy.inference_semantics": "pointwise_features",
            }
        )

        train_raw, val_raw, test_raw = load_and_split_data(
            data_dir=data_dir,
            train_file=args.train_file,
            val_file=args.val_file,
            train_trips=args.train_trips,
            val_trips=args.val_trips,
            test_trips=args.test_trips,
            seed=args.seed,
        )

        train_df = extract_advanced_features_v3(train_raw)
        val_df = extract_advanced_features_v3(val_raw)
        test_df = extract_advanced_features_v3(test_raw)

        params = {**DEFAULT_MODEL_PARAMS, "random_state": args.seed}
        model = train_model(train_df, val_df, params)

        mlflow.log_params(
            {
                **params,
                "train_trip_limit": args.train_trips,
                "val_trip_limit": args.val_trips,
                "test_trip_limit": args.test_trips,
                "chunk_size": args.chunk_size,
                "smoothing_window": args.smoothing_window,
                "min_segment_len": args.min_segment_len,
                "feature_count": len(FEATURES),
            }
        )
        mlflow.log_metrics(
            {
                "train_rows": float(len(train_df)),
                "val_rows": float(len(val_df)),
                "test_rows": float(len(test_df)),
            }
        )

        metrics, report = evaluate_with_smoothing(
            test_df,
            model,
            chunk_size=args.chunk_size,
            smoothing_window=args.smoothing_window,
            min_segment_len=args.min_segment_len,
        )
        mlflow.log_metrics(metrics)

        mlflow.log_dict({"features": FEATURES}, "contracts/features.json")
        mlflow.log_dict(
            {
                "original_mode_names": ORIGINAL_MODE_NAMES,
                "train_to_compact": TRAIN_TO_COMPACT,
                "compact_to_original": COMPACT_TO_ORIGINAL,
            },
            "contracts/label_mapping.json",
        )
        mlflow.log_dict(report, "evaluation/classification_report_smoothed.json")
        mlflow.log_text(
            json.dumps(
                {
                    "required_raw_columns": [
                        "trip_id",
                        "latitude",
                        "longitude",
                        "timestamp",
                    ],
                    "model_input": "17 engineered numeric features",
                    "model_output": "compact class id 0..4",
                    "smoothing_packaged_in_model": False,
                },
                indent=2,
            ),
            "contracts/runtime_contract.json",
        )

        input_example = train_df[FEATURES].head(5)
        prediction_example = model.predict(input_example)
        signature = infer_signature(input_example, prediction_example)

        log_kwargs: dict[str, Any] = {
            "lgb_model": model,
            "name": "model",
            "signature": signature,
            "input_example": input_example,
        }
        if args.registered_model_name:
            log_kwargs["registered_model_name"] = args.registered_model_name

        mlflow.lightgbm.log_model(**log_kwargs)

        print(f"MLflow run_id={run.info.run_id}")
        print(f"Experiment={args.experiment_name}")
        print(f"Smoothed test accuracy={metrics['test_accuracy_smoothed']:.4f}")
        print(f"Smoothed test macro F1={metrics['test_macro_f1_smoothed']:.4f}")
        return run.info.run_id


def main() -> None:
    run_training(parse_args())


if __name__ == "__main__":
    main()

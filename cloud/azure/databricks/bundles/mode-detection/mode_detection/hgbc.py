"""HGBC implementation of the generic mode-detection contract."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .contract import ModeDetectingModel, ModeModelMetadata, ModePrediction, Observation
from .hgbc_features import HGBC_FEATURE_COLUMNS, compute_hgbc_features

DEFAULT_MODEL_NAME = "aihub_canonical_raw120_hgbc"


class HGBCModeDetectingModel(ModeDetectingModel):
    """Run the canonical raw-120 HistGradientBoosting model."""

    def __init__(
        self,
        artifact_path: str | Path,
        *,
        prediction_stride_seconds: int = 10,
        bundle_loader: Callable[[str | Path], Any] | None = None,
    ) -> None:
        if prediction_stride_seconds <= 0:
            raise ValueError("prediction_stride_seconds must be positive")
        self._artifact_path = Path(artifact_path)
        self._bundle = (bundle_loader or self._load_bundle)(self._artifact_path)
        self._validate_bundle(self._bundle)

        feature_columns = tuple(self._bundle["feature_columns"])
        if feature_columns != HGBC_FEATURE_COLUMNS:
            raise ValueError(
                "HGBC artifact feature contract does not match robust 16-feature runtime"
            )

        window_seconds = int(self._bundle.get("window_duration_seconds", 0))
        if window_seconds != 120:
            raise ValueError("HGBC baseline must use a 120-second window")

        selected = self._bundle.get("selected_candidate")
        self._metadata = ModeModelMetadata(
            model_name=DEFAULT_MODEL_NAME,
            model_version=str(selected or self._artifact_path.name),
            feature_version=str(self._bundle.get("feature_version", "unknown")),
            window_seconds=window_seconds,
            prediction_stride_seconds=prediction_stride_seconds,
        )

    @staticmethod
    def _load_bundle(path: str | Path) -> Any:
        import joblib
        return joblib.load(path)

    @staticmethod
    def _validate_bundle(bundle: Any) -> None:
        if not isinstance(bundle, dict):
            raise ValueError("HGBC artifact must be a dictionary bundle")
        required = {"model", "feature_columns", "classes", "window_duration_seconds"}
        missing = required - set(bundle)
        if missing:
            raise ValueError(f"HGBC artifact missing keys: {sorted(missing)}")
        if not hasattr(bundle["model"], "predict_proba"):
            raise ValueError("HGBC artifact model must expose predict_proba")
        if not tuple(str(value) for value in bundle["classes"]):
            raise ValueError("HGBC artifact classes must not be empty")

    @property
    def metadata(self) -> ModeModelMetadata:
        return self._metadata

    def _window(
        self,
        observations: Sequence[Observation],
        *,
        window_end: datetime,
    ) -> tuple[Observation, ...]:
        if len(observations) < 2:
            raise ValueError("HGBC prediction requires at least two observations")

        window_start = window_end - timedelta(seconds=self._metadata.window_seconds)
        selected = tuple(sorted(
            (
                point
                for point in observations
                if window_start <= point.event_time <= window_end
            ),
            key=lambda point: point.event_time,
        ))
        if len(selected) < 2:
            raise ValueError("full HGBC window does not contain enough observations")

        observed_span = (selected[-1].event_time - selected[0].event_time).total_seconds()
        if observed_span < self._metadata.window_seconds:
            raise ValueError(
                "HGBC prediction requires observations spanning the complete 120-second window"
            )
        return selected

    def prediction_ready(
        self,
        observations: Sequence[Observation],
        *,
        window_end: datetime,
    ) -> bool:
        try:
            self._window(observations, window_end=window_end)
        except ValueError:
            return False
        return True

    def predict(
        self,
        observations: Sequence[Observation],
        *,
        window_end: datetime,
        raw_point_count: int,
    ) -> ModePrediction:
        window = self._window(observations, window_end=window_end)
        features = compute_hgbc_features(window, raw_point_count=raw_point_count)

        import pandas as pd

        frame = pd.DataFrame(
            [[features[name] for name in HGBC_FEATURE_COLUMNS]],
            columns=HGBC_FEATURE_COLUMNS,
        )
        probabilities = self._bundle["model"].predict_proba(frame)[0]
        classes = [str(value) for value in self._bundle["classes"]]
        if len(probabilities) != len(classes):
            raise ValueError("HGBC probability output does not match class contract")
        probability_map = {
            name: float(value)
            for name, value in zip(classes, probabilities, strict=True)
        }
        predicted_mode = max(probability_map, key=probability_map.get)

        return ModePrediction(
            predicted_mode=predicted_mode,
            confidence=probability_map[predicted_mode],
            probabilities=probability_map,
            window_start=window_end - timedelta(seconds=self._metadata.window_seconds),
            window_end=window_end,
            metadata=self._metadata,
        )

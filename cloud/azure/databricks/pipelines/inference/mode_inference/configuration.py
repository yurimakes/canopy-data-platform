"""Validated Pipeline B table and runtime configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_SCHEMAS = {"information_schema"}


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value


@dataclass(frozen=True)
class ModeInferenceConfig:
    catalog: str = "dbw_canopy_trial"
    silver_schema: str = "sandbox"
    input_observations_name: str = "silver_gps_observations"
    output_predictions_name: str = "silver_mode_predictions"
    model_uri: str = "models:/dbw_canopy_trial.ml.canopy_transition_lgbm_pointwise/1"
    model_artifact_path: str = "/Volumes/dbw_canopy_trial/ml/runtime_artifacts/canopy_transition_lgbm_pointwise_v1.skops"
    state_timeout: str = "2h"
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        for field in (
            "catalog", "silver_schema", "input_observations_name", "output_predictions_name"
        ):
            _identifier(getattr(self, field), field)
        if self.silver_schema.lower() in _RESERVED_SCHEMAS:
            raise ValueError("reserved schema is not allowed")
        if self.input_observations_name == self.output_predictions_name:
            raise ValueError("input and output tables must be distinct")
        if not self.model_uri.startswith("models:/"):
            raise ValueError("model_uri must be an MLflow models:/ URI")
        if not self.model_artifact_path.startswith("/Volumes/"):
            raise ValueError("model_artifact_path must be a Unity Catalog Volume path")
        timeout = self.state_timeout.strip().lower()
        if not re.fullmatch(r"[1-9][0-9]*[smh]", timeout):
            raise ValueError(
                "state_timeout must be a positive duration such as 30m, 2h, or 7200s"
            )
        if self.timezone.strip().upper() != "UTC":
            raise ValueError("only UTC is supported")

    @property
    def input_table(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.input_observations_name}"

    @property
    def output_table(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.output_predictions_name}"


_STATE_TIMEOUT_MULTIPLIERS_MS = {
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
}


def state_timeout_ms(value: str) -> int:
    """Parse validated compact state timeout strings into milliseconds."""
    normalized = value.strip().lower()
    match = re.fullmatch(r"([1-9][0-9]*)([smh])", normalized)
    if match is None:
        raise ValueError(
            "state_timeout must be a positive duration such as 30m, 2h, or 7200s"
        )
    quantity, unit = match.groups()
    return int(quantity) * _STATE_TIMEOUT_MULTIPLIERS_MS[unit]

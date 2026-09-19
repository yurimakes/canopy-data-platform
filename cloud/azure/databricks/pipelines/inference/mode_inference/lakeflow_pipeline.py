"""Lakeflow Pipeline B: observations to pointwise transportation-mode predictions."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from mode_inference.configuration import ModeInferenceConfig
from mode_inference.contracts import MODE_PREDICTIONS_SCHEMA_DDL
from mode_inference.model_inference import infer_predictions
from mode_inference.state import stateful_feature_rows


def _spark() -> SparkSession:
    session = SparkSession.getActiveSession()
    if session is None:
        raise RuntimeError("Lakeflow pipeline requires an active SparkSession")
    return session


def _conf(name: str) -> str:
    value = _spark().conf.get(f"canopy.{name}")
    if not value or not value.strip():
        raise ValueError(f"missing configuration canopy.{name}")
    return value.strip()


CONFIG = ModeInferenceConfig(
    catalog=_conf("catalog"),
    silver_schema=_conf("silver_schema"),
    input_observations_name=_conf("input_observations_table"),
    output_predictions_name=_conf("output_predictions_table"),
    model_uri=_conf("transition_model_uri"),
    model_artifact_path=_conf("transition_model_artifact_path"),
    state_timeout=_conf("state_timeout"),
    timezone=_spark().conf.get("spark.sql.session.timeZone"),
)
@dp.table(
    name=CONFIG.output_table,
    schema=MODE_PREDICTIONS_SCHEMA_DDL,
    comment="Raw pointwise LightGBM transportation-mode predictions; no smoothing or segmentation.",
)
def mode_predictions():
    observations = _spark().readStream.table(CONFIG.input_table)
    features = stateful_feature_rows(observations)
    return infer_predictions(
        features,
        _spark(),
        CONFIG.model_uri,
        CONFIG.model_artifact_path,
    )

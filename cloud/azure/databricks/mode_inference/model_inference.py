"""MLflow Spark inference and compact-class output projection."""

from __future__ import annotations

import re
from typing import Any

from .contracts import FEATURE_NAMES, MODE_BY_CLASS

_VERSION_URI = re.compile(r"^models:/([^@]+)/(\d+)$")
_ALIAS_URI = re.compile(r"^models:/([^@]+)@([^/]+)$")


def model_identity(model_uri: str) -> tuple[str, str | None]:
    if match := _VERSION_URI.fullmatch(model_uri):
        return match.group(1), match.group(2)
    if match := _ALIAS_URI.fullmatch(model_uri):
        return match.group(1), None
    raise ValueError("model URI must use models:/<name>/<version> or models:/<name>@<alias>")


def mode_for_class(predicted_class: int) -> str:
    try:
        return MODE_BY_CLASS[int(predicted_class)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unsupported compact class: {predicted_class!r}") from exc


def predict_pandas(model: Any, frame: Any) -> Any:
    """Shared local parity seam that enforces names and order before prediction."""
    return model.predict(frame.loc[:, list(FEATURE_NAMES)])


def infer_predictions(features: Any, spark: Any, model_uri: str) -> Any:
    import mlflow.pyfunc
    from pyspark.sql import functions as F

    model_name, model_version = model_identity(model_uri)
    predict = mlflow.pyfunc.spark_udf(
        spark, model_uri=model_uri, result_type="long", env_manager="local"
    )
    mapping_items = []
    for compact_class, mode in MODE_BY_CLASS.items():
        mapping_items.extend((F.lit(compact_class), F.lit(mode)))
    mode_map = F.create_map(*mapping_items)
    predicted = features.withColumn(
        "predicted_class",
        predict(F.struct(*[F.col(name) for name in FEATURE_NAMES])).cast("int"),
    )
    return predicted.select(
        "event_id", "user_id", "trip_id", "sequence", "event_time",
        F.col("predicted_class"),
        mode_map[F.col("predicted_class")].alias("predicted_mode"),
        F.lit(None).cast("double").alias("confidence"),
        F.lit(model_name).alias("model_name"),
        F.lit(model_version).cast("string").alias("model_version"),
        F.current_timestamp().alias("predicted_at"),
    )

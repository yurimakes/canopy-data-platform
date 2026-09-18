"""Low-overhead pointwise inference for the Lakeflow streaming pipeline."""

from __future__ import annotations

import re
from typing import Any

from .contracts import FEATURE_NAMES, MODE_BY_CLASS

_VERSION_URI = re.compile(r"^models:/([^@]+)/(\d+)$")
_ALIAS_URI = re.compile(r"^models:/([^@]+)@([^/]+)$")

# Python workers are reused across Arrow batches. Keep one loaded pyfunc model
# per URI in each worker process instead of constructing an MLflow Spark UDF
# environment for every streaming query.
_MODEL_CACHE: dict[str, Any] = {}


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
    """Shared parity seam that enforces model feature names and order."""
    return model.predict(frame.loc[:, list(FEATURE_NAMES)])


def _load_worker_model(model_uri: str) -> Any:
    """Load and cache the registered MLflow model once per Python worker."""
    model = _MODEL_CACHE.get(model_uri)
    if model is None:
        import mlflow.pyfunc

        model = mlflow.pyfunc.load_model(model_uri)
        _MODEL_CACHE[model_uri] = model
    return model


def _prediction_udf(model_uri: str) -> Any:
    """Build a scalar Pandas UDF without MLflow Spark-UDF sandbox setup."""
    import pandas as pd
    from pyspark.sql.functions import PandasUDFType, pandas_udf
    from pyspark.sql.types import LongType

    @pandas_udf(LongType(), PandasUDFType.SCALAR)
    def predict(frame):
        ordered = frame.loc[:, list(FEATURE_NAMES)]
        model = _load_worker_model(model_uri)
        values = predict_pandas(model, ordered)
        return pd.Series(values, index=ordered.index, dtype="int64")

    return predict


def infer_predictions(features: Any, spark: Any, model_uri: str) -> Any:
    """Apply the registered model in-process on Python workers."""
    del spark

    from pyspark.sql import functions as F

    model_name, model_version = model_identity(model_uri)
    predict = _prediction_udf(model_uri)

    mapping_items = []
    for compact_class, mode in MODE_BY_CLASS.items():
        mapping_items.extend((F.lit(compact_class), F.lit(mode)))
    mode_map = F.create_map(*mapping_items)

    predicted = features.withColumn(
        "predicted_class",
        predict(
            F.struct(*[F.col(name).alias(name) for name in FEATURE_NAMES])
        ).cast("int"),
    )

    return predicted.select(
        "event_id", "user_id", "trip_id", "sequence", "event_time",
        F.col("predicted_class"),
        mode_map[F.col("predicted_class")].alias("predicted_mode"),
        F.lit(None).cast("double").alias("confidence"),
        F.lit(model_name).alias("model_name"),
        F.lit(model_version).cast("string").alias("model_version"),
        F.col("features_processed_at"),
        F.current_timestamp().alias("predicted_at"),
    )

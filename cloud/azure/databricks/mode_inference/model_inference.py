"""Low-overhead pointwise inference for the Lakeflow streaming pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import FEATURE_NAMES, MODE_BY_CLASS

_VERSION_URI = re.compile(r"^models:/([^@]+)/(\d+)$")
_ALIAS_URI = re.compile(r"^models:/([^@]+)@([^/]+)$")

_MODEL_ARTIFACT = (
    Path(__file__).resolve().parent
    / "artifacts"
    / "transition_lgbm_v1"
    / "model.skops"
)

_SKOPS_TRUSTED_TYPES = [
    "collections.OrderedDict",
    "lightgbm.sklearn.LGBMClassifier",
    "lightgbm.sklearn.LGBMRegressor",
    "lightgbm.basic.Booster",
]

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


def _load_driver_model() -> Any:
    """Load the bundled native LGBMClassifier without MLflow runtime I/O."""
    if not _MODEL_ARTIFACT.exists():
        raise FileNotFoundError(
            f"bundled model artifact is missing: {_MODEL_ARTIFACT}"
        )

    import skops.io as sio

    return sio.load(
        _MODEL_ARTIFACT,
        trusted=_SKOPS_TRUSTED_TYPES,
    )


def _load_worker_model(cache_key: str, model_bytes: bytes) -> Any:
    """Deserialize the bundled native estimator once per Python worker."""
    model = _MODEL_CACHE.get(cache_key)
    if model is None:
        import cloudpickle

        model = cloudpickle.loads(model_bytes)
        _MODEL_CACHE[cache_key] = model
    return model


def _prediction_udf(model_uri: str) -> Any:
    """Build a scalar Pandas UDF from the bundled native LightGBM model."""
    import cloudpickle
    import pandas as pd
    from pyspark.sql.functions import PandasUDFType, pandas_udf
    from pyspark.sql.types import LongType, StructField, StructType, TimestampType

    driver_model = _load_driver_model()
    model_bytes = cloudpickle.dumps(driver_model)
    cache_key = f"{model_uri}:{_MODEL_ARTIFACT.name}"

    result_schema = StructType([
        StructField("predicted_class", LongType(), nullable=False),
        StructField("predicted_at", TimestampType(), nullable=False),
    ])

    @pandas_udf(result_schema, PandasUDFType.SCALAR)
    def predict(frame):
        ordered = frame.loc[:, list(FEATURE_NAMES)]
        model = _load_worker_model(cache_key, model_bytes)
        values = predict_pandas(model, ordered)

        completed_at = pd.Timestamp.now(tz="UTC").tz_localize(None)

        return pd.DataFrame(
            {
                "predicted_class": pd.Series(
                    values, index=ordered.index, dtype="int64"
                ),
                "predicted_at": pd.Series(
                    completed_at, index=ordered.index, dtype="datetime64[ns]"
                ),
            }
        )

    return predict


def infer_predictions(features: Any, spark: Any, model_uri: str) -> Any:
    """Apply the bundled model in-process on Python workers."""
    del spark

    from pyspark.sql import functions as F

    model_name, model_version = model_identity(model_uri)
    predict = _prediction_udf(model_uri)

    mapping_items = []
    for compact_class, mode in MODE_BY_CLASS.items():
        mapping_items.extend((F.lit(compact_class), F.lit(mode)))
    mode_map = F.create_map(*mapping_items)

    predicted = features.withColumn(
        "_prediction",
        predict(
            F.struct(*[F.col(name).alias(name) for name in FEATURE_NAMES])
        ),
    ).withColumn(
        "predicted_class",
        F.col("_prediction.predicted_class").cast("int"),
    )

    return predicted.select(
        "event_id", "user_id", "trip_id", "sequence", "event_time",
        F.col("predicted_class"),
        mode_map[F.col("predicted_class")].alias("predicted_mode"),
        F.lit(None).cast("double").alias("confidence"),
        F.lit(model_name).alias("model_name"),
        F.lit(model_version).cast("string").alias("model_version"),
        F.col("features_processed_at"),
        F.col("_prediction.predicted_at").alias("predicted_at"),
    )

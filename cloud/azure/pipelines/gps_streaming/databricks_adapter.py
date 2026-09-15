"""Databricks/Delta adapter for bounded closed-segment inference.

PySpark, Delta Lake, and MLflow imports stay inside runtime functions so the
domain package and its unit tests remain usable outside Databricks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable

from .mock_detector import SegmentEvent
from .segment_inference import SegmentInferenceResult, infer_closed_segment


_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class DatabricksInferenceConfig:
    """Workspace values supplied by a Databricks job or Asset Bundle."""

    model_uri: str
    checkpoint_location: str
    gps_features_table: str = "canopy.silver.gps_features"
    segments_table: str = "canopy.silver.mode_segments"
    predictions_table: str = "canopy.gold.mode_segment_predictions"
    query_name: str = "canopy-speedtransformer-segment-inference"

    def __post_init__(self) -> None:
        if not self.model_uri.strip():
            raise ValueError("model_uri is required")
        if not self.checkpoint_location.strip():
            raise ValueError("checkpoint_location is required")
        for value in (
            self.gps_features_table,
            self.segments_table,
            self.predictions_table,
        ):
            if not _TABLE_NAME.fullmatch(value):
                raise ValueError(f"expected catalog.schema.table, got {value!r}")


def ensure_prediction_table(spark: Any, config: DatabricksInferenceConfig) -> None:
    """Create only the downstream table owned by this adapter."""
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {config.predictions_table} (
          trip_id STRING NOT NULL,
          user_id STRING NOT NULL,
          segment_id STRING NOT NULL,
          start_time TIMESTAMP NOT NULL,
          end_time TIMESTAMP NOT NULL,
          weak_mode STRING NOT NULL,
          weak_confidence DOUBLE NOT NULL,
          detector_version STRING NOT NULL,
          inference_status STRING NOT NULL,
          strong_mode STRING,
          strong_confidence DOUBLE,
          probabilities ARRAY<DOUBLE>,
          window_count INT NOT NULL,
          speed_point_count INT NOT NULL,
          model_uri STRING NOT NULL,
          stream_batch_id BIGINT NOT NULL,
          processed_at TIMESTAMP NOT NULL
        ) USING DELTA
        """
    )


def build_foreach_batch_handler(
    spark: Any,
    config: DatabricksInferenceConfig,
    *,
    model_loader: Callable[[str], Any] | None = None,
) -> Callable[[Any, int], None]:
    """Return a handler suitable for ``DataStreamWriter.foreachBatch``."""
    if model_loader is None:
        import mlflow

        model_loader = mlflow.pyfunc.load_model

    loaded_model: Any | None = None

    def get_model() -> Any:
        nonlocal loaded_model
        if loaded_model is None:
            loaded_model = model_loader(config.model_uri)
        return loaded_model

    def handler(segments_batch: Any, batch_id: int) -> None:
        infer_segments_microbatch(
            spark,
            segments_batch,
            batch_id,
            config,
            get_model=get_model,
        )

    return handler


def start_segment_inference_stream(
    spark: Any,
    config: DatabricksInferenceConfig,
    *,
    trigger_interval: str = "10 seconds",
) -> Any:
    """Start the closed-segment stream and return its StreamingQuery."""
    ensure_prediction_table(spark, config)
    handler = build_foreach_batch_handler(spark, config)
    return (
        spark.readStream.table(config.segments_table)
        .where("status = 'closed'")
        .writeStream.queryName(config.query_name)
        .option("checkpointLocation", config.checkpoint_location)
        .trigger(processingTime=trigger_interval)
        .foreachBatch(handler)
        .start()
    )


def infer_segments_microbatch(
    spark: Any,
    segments_batch: Any,
    batch_id: int,
    config: DatabricksInferenceConfig,
    *,
    get_model: Callable[[], Any],
) -> None:
    """Join finite segment history, score on the driver, then Delta-MERGE."""
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        ArrayType,
        DoubleType,
        IntegerType,
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    closed = segments_batch.where(F.col("status") == "closed")
    already_scored = (
        spark.table(config.predictions_table)
        .where(F.col("inference_status") == "scored")
        .select("segment_id")
    )
    pending = closed.join(already_scored, "segment_id", "left_anti")

    segments = pending.alias("s")
    gps = spark.table(config.gps_features_table).alias("g")
    within_segment = (
        (F.col("g.trip_id") == F.col("s.trip_id"))
        & (F.col("g.event_time") >= F.col("s.start_time"))
        & (F.col("g.event_time") <= F.col("s.end_time"))
    )
    group_columns = [
        "segment_id",
        "trip_id",
        "user_id",
        "start_time",
        "end_time",
        "speed_point_count",
        "weak_mode",
        "weak_confidence",
        "detector_version",
    ]
    history = (
        segments.join(gps, within_segment, "left")
        .select(
            *(F.col(f"s.{name}").alias(name) for name in group_columns),
            F.when(
                F.col("g.derived_speed_kmh").isNotNull(),
                F.struct(
                    F.col("g.event_time").alias("event_time"),
                    F.col("g.sequence").alias("sequence"),
                    F.col("g.derived_speed_kmh").alias("derived_speed_kmh"),
                ),
            ).alias("point"),
        )
        .groupBy(*group_columns)
        .agg(F.sort_array(F.collect_list("point")).alias("points"))
    )

    result_rows = []
    model: Any | None = None
    processed_at = datetime.now(timezone.utc)
    for row in history.toLocalIterator():
        segment = SegmentEvent(
            trip_id=row.trip_id,
            user_id=row.user_id,
            segment_id=row.segment_id,
            start_time=row.start_time,
            end_time=row.end_time,
            speed_point_count=row.speed_point_count,
            weak_mode=row.weak_mode,
            weak_confidence=row.weak_confidence,
            status="closed",
            detector_version=row.detector_version,
        )
        speeds = [point.derived_speed_kmh for point in row.points]
        if len(speeds) == segment.speed_point_count and len(speeds) >= 200:
            if model is None:
                model = get_model()
        result = infer_closed_segment(segment, speeds, model)
        result_rows.append(
            prediction_row(
                result,
                model_uri=config.model_uri,
                batch_id=batch_id,
                processed_at=processed_at,
            )
        )

    if not result_rows:
        return

    schema = StructType(
        [
            StructField("trip_id", StringType(), False),
            StructField("user_id", StringType(), False),
            StructField("segment_id", StringType(), False),
            StructField("start_time", TimestampType(), False),
            StructField("end_time", TimestampType(), False),
            StructField("weak_mode", StringType(), False),
            StructField("weak_confidence", DoubleType(), False),
            StructField("detector_version", StringType(), False),
            StructField("inference_status", StringType(), False),
            StructField("strong_mode", StringType(), True),
            StructField("strong_confidence", DoubleType(), True),
            StructField("probabilities", ArrayType(DoubleType()), True),
            StructField("window_count", IntegerType(), False),
            StructField("speed_point_count", IntegerType(), False),
            StructField("model_uri", StringType(), False),
            StructField("stream_batch_id", LongType(), False),
            StructField("processed_at", TimestampType(), False),
        ]
    )
    updates = spark.createDataFrame(result_rows, schema=schema)
    target = DeltaTable.forName(spark, config.predictions_table)
    (
        target.alias("target")
        .merge(updates.alias("updates"), "target.segment_id = updates.segment_id")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def prediction_row(
    result: SegmentInferenceResult,
    *,
    model_uri: str,
    batch_id: int,
    processed_at: datetime,
) -> dict[str, Any]:
    """Convert domain output to the stable Delta prediction schema."""
    values = asdict(result)
    values["inference_status"] = values.pop("status")
    values["probabilities"] = (
        None if values["probabilities"] is None else list(values["probabilities"])
    )
    values.update(
        model_uri=model_uri,
        stream_batch_id=int(batch_id),
        processed_at=processed_at,
    )
    return values

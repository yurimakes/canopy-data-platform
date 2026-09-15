"""Stateful GPS feature and mock-segmentation primitives."""

from .pipeline import EnrichedSpeedPoint, MockFirstLayerPipeline
from .mock_detector import MockDetectorConfig, MockFirstLayerDetector, SegmentEvent
from .segment_inference import SegmentInferenceResult, infer_closed_segment
from .windowing import SpeedWindow, build_speed_windows
from .databricks_adapter import DatabricksInferenceConfig
from .deployment_config import CanopyTableConfig
from .gps_preprocessing import (
    DerivedGpsPoint,
    GpsFirstLayerRuntime,
    GpsObservation,
    GpsRuntimeOutput,
    GpsTransitionProcessor,
)
from .spark_ingestion import SparkIngestionConfig
from .transform_with_state import (
    CanopyGpsStatefulProcessor,
    TransformWithStateConfig,
)

__all__ = [
    "EnrichedSpeedPoint",
    "CanopyTableConfig",
    "CanopyGpsStatefulProcessor",
    "DatabricksInferenceConfig",
    "DerivedGpsPoint",
    "GpsFirstLayerRuntime",
    "GpsObservation",
    "GpsRuntimeOutput",
    "GpsTransitionProcessor",
    "MockDetectorConfig",
    "MockFirstLayerDetector",
    "MockFirstLayerPipeline",
    "SparkIngestionConfig",
    "TransformWithStateConfig",
    "SegmentInferenceResult",
    "SegmentEvent",
    "SpeedWindow",
    "build_speed_windows",
    "infer_closed_segment",
]

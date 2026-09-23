"""Stateful GPS feature and mock-segmentation primitives."""

from .databricks_adapter import DatabricksInferenceConfig
from .deployment_config import CanopyTableConfig
from .gps_preprocessing import (
    DerivedGpsPoint,
    GpsFirstLayerRuntime,
    GpsObservation,
    GpsRuntimeOutput,
    GpsTransitionProcessor,
)
from .mock_detector import MockDetectorConfig, MockFirstLayerDetector, SegmentEvent
from .pipeline import EnrichedSpeedPoint, MockFirstLayerPipeline
from .segment_inference import SegmentInferenceResult, infer_closed_segment
from .spark_ingestion import SparkIngestionConfig
from .transform_with_state import (
    CanopyGpsStatefulProcessor,
    TransformWithStateConfig,
)
from .windowing import SpeedWindow, build_speed_windows

__all__ = [
    "CanopyGpsStatefulProcessor",
    "CanopyTableConfig",
    "DatabricksInferenceConfig",
    "DerivedGpsPoint",
    "EnrichedSpeedPoint",
    "GpsFirstLayerRuntime",
    "GpsObservation",
    "GpsRuntimeOutput",
    "GpsTransitionProcessor",
    "MockDetectorConfig",
    "MockFirstLayerDetector",
    "MockFirstLayerPipeline",
    "SegmentEvent",
    "SegmentInferenceResult",
    "SparkIngestionConfig",
    "SpeedWindow",
    "TransformWithStateConfig",
    "build_speed_windows",
    "infer_closed_segment",
]

"""Stateful GPS feature and mock-segmentation primitives."""

from .pipeline import EnrichedSpeedPoint, MockFirstLayerPipeline
from .mock_detector import MockDetectorConfig, MockFirstLayerDetector, SegmentEvent
from .segment_inference import SegmentInferenceResult, infer_closed_segment
from .windowing import SpeedWindow, build_speed_windows
from .databricks_adapter import DatabricksInferenceConfig
from .gps_preprocessing import (
    DerivedGpsPoint,
    GpsFirstLayerRuntime,
    GpsObservation,
    GpsRuntimeOutput,
    GpsTransitionProcessor,
)

__all__ = [
    "EnrichedSpeedPoint",
    "DatabricksInferenceConfig",
    "DerivedGpsPoint",
    "GpsFirstLayerRuntime",
    "GpsObservation",
    "GpsRuntimeOutput",
    "GpsTransitionProcessor",
    "MockDetectorConfig",
    "MockFirstLayerDetector",
    "MockFirstLayerPipeline",
    "SegmentInferenceResult",
    "SegmentEvent",
    "SpeedWindow",
    "build_speed_windows",
    "infer_closed_segment",
]

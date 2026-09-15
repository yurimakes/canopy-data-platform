"""Stateful GPS feature and mock-segmentation primitives."""

from .pipeline import EnrichedSpeedPoint, MockFirstLayerPipeline
from .mock_detector import MockDetectorConfig, MockFirstLayerDetector, SegmentEvent

__all__ = [
    "EnrichedSpeedPoint",
    "MockDetectorConfig",
    "MockFirstLayerDetector",
    "MockFirstLayerPipeline",
    "SegmentEvent",
]

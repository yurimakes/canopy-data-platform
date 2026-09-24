"""Transit-context adaptation for mode predictions.

This module keeps per-trip transit history small and injects the concrete
reference/evidence resolver so streaming state stays independent of reference
file loading and spatial-index construction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contract import ModePrediction, Observation


TransitResolver = Callable[
    [Mapping[str, float], Sequence[Observation], Sequence[tuple[str, str]]],
    tuple[Mapping[str, Any], Mapping[str, Any]],
]


@dataclass(frozen=True)
class TransitAdjustedPrediction:
    raw_prediction: ModePrediction
    final_mode: str
    confidence: float
    decision_status: str
    correction_applied: bool
    correction_reason: str
    context: Mapping[str, Any]


@dataclass
class TransitContextState:
    station_history: list[tuple[str, str]] = field(default_factory=list)

    def apply(
        self,
        prediction: ModePrediction,
        observations: Sequence[Observation],
        *,
        resolver: TransitResolver,
    ) -> TransitAdjustedPrediction:
        """Apply transit evidence to one model prediction and update history."""

        decision, context = resolver(
            prediction.probabilities,
            observations,
            tuple(self.station_history),
        )

        final_mode = str(decision["final_mode"])
        confidence = float(decision["decision_confidence"])

        observed_station_ids = context.get(
            "subway_current_observed_station_ids",
            (),
        ) or ()
        matched_line = context.get("matched_subway_line")
        if matched_line is not None:
            line = str(matched_line)
            for station_id in observed_station_ids:
                item = (str(station_id), line)
                if item not in self.station_history:
                    self.station_history.append(item)

        return TransitAdjustedPrediction(
            raw_prediction=prediction,
            final_mode=final_mode,
            confidence=confidence,
            decision_status=str(decision.get("decision_status", "unknown")),
            correction_applied=bool(decision.get("correction_applied", False)),
            correction_reason=str(decision.get("correction_reason", "")),
            context=dict(context),
        )

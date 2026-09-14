from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


class CarbonCalculationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SegmentCarbonResult:
    segment_id: str | None
    predicted_mode: str | None
    user_confirmed_mode: str | None
    effective_mode: str
    distance_m: float
    emission_kgco2e_raw: float


@dataclass(frozen=True)
class TripCarbonResult:
    policy_version: str
    factor_version: str
    distance_km: float
    emission_kgco2e: float
    segments: tuple[SegmentCarbonResult, ...]


def load_policy(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        policy = yaml.safe_load(f)
    validate_policy(policy)
    return policy


def validate_policy(policy: Mapping[str, Any]) -> None:
    required = (
        "policy_version",
        "factor_version",
        "supported_modes",
        "distance",
        "output",
        "mode_resolution",
        "factors",
    )
    missing = [key for key in required if key not in policy]
    if missing:
        raise CarbonCalculationError(
            "invalid_policy",
            f"Missing policy keys: {', '.join(missing)}",
        )

    supported = set(policy["supported_modes"])
    for mode in supported:
        factor = policy["factors"].get(mode)
        if factor is None or factor.get("value") is None:
            raise CarbonCalculationError(
                "missing_factor",
                f"Factor value is not configured for mode={mode}",
            )

    if policy["distance"].get("input_unit") != "m":
        raise CarbonCalculationError(
            "invalid_policy",
            "segment distance input must be meters.",
        )
    if policy["output"].get("emission_unit") != "kgCO2e":
        raise CarbonCalculationError(
            "invalid_policy",
            "output emission unit must be kgCO2e.",
        )


def resolve_effective_mode(
    segment: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    supported = set(policy["supported_modes"])

    for field in policy["mode_resolution"]["precedence"]:
        raw = segment.get(field)
        if raw is None or not str(raw).strip():
            continue

        mode = str(raw).strip().lower()
        if mode not in supported:
            raise CarbonCalculationError(
                "unsupported_mode",
                f"Unsupported mode={mode}",
            )
        return mode

    raise CarbonCalculationError(
        "missing_mode",
        "No usable user_confirmed_mode or predicted_mode was found.",
    )


def _distance_m(segment: Mapping[str, Any]) -> Decimal:
    raw = segment.get("distance_m")
    if raw is None:
        raise CarbonCalculationError(
            "missing_distance",
            f"distance_m is missing for segment_id={segment.get('segment_id')}",
        )
    try:
        value = Decimal(str(raw))
    except Exception as exc:
        raise CarbonCalculationError(
            "invalid_distance",
            f"distance_m is not numeric: {raw!r}",
        ) from exc

    if value < 0:
        raise CarbonCalculationError(
            "negative_distance",
            f"distance_m must be >= 0, got {value}",
        )
    return value


def _factor(mode: str, policy: Mapping[str, Any]) -> Decimal:
    factor = policy["factors"].get(mode)
    if factor is None or factor.get("value") is None:
        raise CarbonCalculationError(
            "missing_factor",
            f"No usable factor for mode={mode}",
        )
    return Decimal(str(factor["value"]))


def calculate_trip_carbon(
    segments: Iterable[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> TripCarbonResult:
    """
    Full-trip recalculation.

    Rules:
    - distance_m -> km
    - factor value is already kgCO2e per relevant km unit
    - user_confirmed_mode overrides predicted_mode
    - previously stored emission is never reused
    - segment raw values are summed first; the trip total is rounded once at the end
    """
    validate_policy(policy)

    meters_per_km = Decimal(str(policy["distance"]["meters_per_km"]))
    storage_decimals = int(policy["output"]["storage_decimals"])

    total_distance_m = Decimal("0")
    total_emission_kg = Decimal("0")
    segment_results: list[SegmentCarbonResult] = []

    for segment in segments:
        effective_mode = resolve_effective_mode(segment, policy)
        distance_m = _distance_m(segment)
        distance_km = distance_m / meters_per_km
        emission_kg = distance_km * _factor(effective_mode, policy)

        total_distance_m += distance_m
        total_emission_kg += emission_kg

        segment_results.append(
            SegmentCarbonResult(
                segment_id=segment.get("segment_id"),
                predicted_mode=segment.get("predicted_mode"),
                user_confirmed_mode=segment.get("user_confirmed_mode"),
                effective_mode=effective_mode,
                distance_m=float(distance_m),
                emission_kgco2e_raw=float(emission_kg),
            )
        )

    quantum = Decimal("1").scaleb(-storage_decimals)
    rounded_total = total_emission_kg.quantize(
        quantum,
        rounding=ROUND_HALF_UP,
    )

    return TripCarbonResult(
        policy_version=str(policy["policy_version"]),
        factor_version=str(policy["factor_version"]),
        distance_km=float(total_distance_m / meters_per_km),
        emission_kgco2e=float(rounded_total),
        segments=tuple(segment_results),
    )


def result_to_dict(result: TripCarbonResult) -> dict[str, Any]:
    return {
        "policy_version": result.policy_version,
        "factor_version": result.factor_version,
        "distance_km": result.distance_km,
        "emission_kgco2e": result.emission_kgco2e,
        "segments": [
            {
                "segment_id": s.segment_id,
                "predicted_mode": s.predicted_mode,
                "user_confirmed_mode": s.user_confirmed_mode,
                "effective_mode": s.effective_mode,
                "distance_m": s.distance_m,
                "emission_kgco2e_raw": s.emission_kgco2e_raw,
            }
            for s in result.segments
        ],
    }

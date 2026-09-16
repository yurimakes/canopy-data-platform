from __future__ import annotations

import math
from typing import Any


def _finite_nonnegative(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0


def classify_behavior_change(
    *,
    weekly_carbon_intensity_g_per_km: float | None,
    personal_baseline_g_per_km: float | None,
    personal_status: str | None,
    personal_method: str | None,
) -> dict[str, Any]:
    """Classify weekly observed carbon reduction independently of mission data."""
    if personal_status != "ready" or personal_method != "personal_cumulative":
        return {
            "status": "insufficient_data",
            "reason": "personal_baseline_not_ready",
            "reduction_g_co2e_per_km": None,
            "reduction_rate": None,
        }

    if not _finite_nonnegative(personal_baseline_g_per_km):
        return {
            "status": "insufficient_data",
            "reason": "personal_baseline_invalid",
            "reduction_g_co2e_per_km": None,
            "reduction_rate": None,
        }

    if not _finite_nonnegative(weekly_carbon_intensity_g_per_km):
        return {
            "status": "insufficient_data",
            "reason": "weekly_carbon_intensity_invalid",
            "reduction_g_co2e_per_km": None,
            "reduction_rate": None,
        }

    baseline = float(personal_baseline_g_per_km)
    actual = float(weekly_carbon_intensity_g_per_km)
    reduction = baseline - actual
    reduction_rate = reduction / baseline if baseline > 0 else None

    return {
        "status": "changed" if reduction > 0 else "no_change",
        "reason": "weekly_carbon_intensity_below_personal_baseline" if reduction > 0 else "weekly_carbon_intensity_not_below_personal_baseline",
        "reduction_g_co2e_per_km": reduction,
        "reduction_rate": reduction_rate,
    }

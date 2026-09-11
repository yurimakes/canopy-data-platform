from __future__ import annotations

from dataclasses import dataclass

from canopy_api.models import TransitRoute


@dataclass(frozen=True)
class RecommendationPolicy:
    max_time_over_fastest_pct: float = 20.0
    max_extra_transfers: int = 1


def recommend_low_carbon_route(
    routes: list[TransitRoute],
    policy: RecommendationPolicy = RecommendationPolicy(),
) -> dict:
    """Choose the lowest-carbon route inside a practical time/transfer envelope."""
    if not routes:
        raise ValueError("No routes to rank")
    if any(route.carbon_g is None for route in routes):
        raise ValueError("Carbon must be calculated before ranking")

    for route in routes:
        route.tags.clear()

    fastest = min(routes, key=lambda r: (r.total_time_s, r.transfer_count))
    lowest_carbon = min(routes, key=lambda r: (r.carbon_g, r.total_time_s))
    fastest.tags.append("fastest")
    if "lowest_carbon" not in lowest_carbon.tags:
        lowest_carbon.tags.append("lowest_carbon")

    max_time_s = fastest.total_time_s * (1.0 + policy.max_time_over_fastest_pct / 100.0)
    max_transfers = fastest.transfer_count + policy.max_extra_transfers
    eligible = [
        route for route in routes
        if route.total_time_s <= max_time_s and route.transfer_count <= max_transfers
    ]
    if not eligible:
        eligible = [fastest]

    recommended = min(eligible, key=lambda r: (r.carbon_g, r.total_time_s, r.transfer_count))
    if "recommended" not in recommended.tags:
        recommended.tags.append("recommended")

    return {
        "policy": {
            "type": "carbon_min_with_practicality_constraint",
            "max_time_over_fastest_pct": policy.max_time_over_fastest_pct,
            "max_extra_transfers": policy.max_extra_transfers,
        },
        "fastest_route_index": fastest.provider_route_index,
        "lowest_carbon_route_index": lowest_carbon.provider_route_index,
        "recommended_route_index": recommended.provider_route_index,
        "recommended_extra_time_s": recommended.total_time_s - fastest.total_time_s,
        "recommended_carbon_saving_vs_fastest_g": round(float(fastest.carbon_g) - float(recommended.carbon_g), 3),
        "eligible_route_indexes": [r.provider_route_index for r in eligible],
        "routes": [r.to_dict() for r in sorted(routes, key=lambda r: (r.carbon_g, r.total_time_s))],
    }

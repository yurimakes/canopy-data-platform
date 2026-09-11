from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from canopy_api.models import TransitRoute


class CarbonFactorError(ValueError):
    pass


@dataclass(frozen=True)
class CarbonFactorSet:
    version: str
    unit: str
    factors: dict[str, float]
    source: str | None = None
    production_approved: bool = False
    boundary: str = "passenger operational travel"

    @classmethod
    def from_json(cls, path: str | Path, allow_unapproved: bool = False) -> "CarbonFactorSet":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        approved = bool(data.get("production_approved", False))
        if not approved and not allow_unapproved:
            raise CarbonFactorError(
                "Carbon factor file is not approved for production. "
                "Set ALLOW_UNAPPROVED_CARBON_FACTORS=true only for demos/tests."
            )
        if data.get("unit") != "gCO2e/passenger-km":
            raise CarbonFactorError("Expected carbon factor unit 'gCO2e/passenger-km'")
        factors = {str(k).upper(): float(v) for k, v in data.get("factors", {}).items() if v is not None}
        return cls(
            version=str(data["version"]),
            unit=data["unit"],
            factors=factors,
            source=data.get("source"),
            production_approved=approved,
            boundary=data.get("boundary", "passenger operational travel"),
        )


def calculate_route_carbon(route: TransitRoute, factor_set: CarbonFactorSet) -> float:
    """Calculate passenger travel emissions by segment distance × mode-specific factor."""
    total = 0.0
    for leg in route.legs:
        mode = leg.mode.upper()
        if mode not in factor_set.factors:
            raise CarbonFactorError(f"Missing carbon factor for mode: {mode}")
        factor = factor_set.factors[mode]
        leg.carbon_factor_g_per_pkm = factor
        leg.carbon_g = (leg.distance_m / 1000.0) * factor
        total += leg.carbon_g

    route.carbon_g = round(total, 3)
    route.carbon_factor_version = factor_set.version
    return route.carbon_g


def calculate_routes_carbon(routes: list[TransitRoute], factor_set: CarbonFactorSet) -> list[TransitRoute]:
    for route in routes:
        calculate_route_carbon(route, factor_set)
    return routes

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class Point:
    lon: float
    lat: float
    name: str | None = None


@dataclass
class TransitLeg:
    mode: str
    distance_m: float
    duration_s: int
    start: Point | None = None
    end: Point | None = None
    route_name: str | None = None
    route_id: str | None = None
    geometry: str | None = None
    carbon_g: float | None = None
    carbon_factor_g_per_pkm: float | None = None


@dataclass
class TransitRoute:
    provider: str
    provider_route_index: int
    total_time_s: int
    total_distance_m: float
    total_walk_distance_m: float
    transfer_count: int
    fare_krw: int | None
    path_type: int | None
    legs: list[TransitLeg] = field(default_factory=list)
    carbon_g: float | None = None
    carbon_factor_version: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

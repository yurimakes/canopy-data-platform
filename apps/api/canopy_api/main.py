from __future__ import annotations

import os
import httpx

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from canopy_api.carbon import CarbonFactorError, CarbonFactorSet, calculate_routes_carbon
from canopy_api.ranking import RecommendationPolicy, recommend_low_carbon_route
from canopy_api.transit.tmap_adapter import normalize_tmap_response
from canopy_api.transit.tmap_client import TmapTransitClient


app = FastAPI(title="Canopy API", version="0.1.0")


class Coordinate(BaseModel):
    lon: float
    lat: float


class LowCarbonRouteRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    count: int = Field(default=10, ge=1, le=10)
    search_dttm: str | None = Field(default=None, description="Optional TMAP time-machine value, yyyymmddhhmi", pattern=r"^\d{12}$")
    max_time_over_fastest_pct: float = Field(default=20.0, ge=0, le=100)
    max_extra_transfers: int = Field(default=1, ge=0, le=5)


def _factor_set() -> CarbonFactorSet:
    configured = os.getenv("CARBON_FACTOR_FILE")
    if not configured:
        raise CarbonFactorError("CARBON_FACTOR_FILE is not configured")
    allow_unapproved = os.getenv("ALLOW_UNAPPROVED_CARBON_FACTORS", "false").lower() == "true"
    return CarbonFactorSet.from_json(configured, allow_unapproved=allow_unapproved)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/routes/low-carbon")
async def low_carbon_routes(req: LowCarbonRouteRequest) -> dict:
    app_key = os.getenv("TMAP_APP_KEY")
    if not app_key:
        raise HTTPException(status_code=503, detail="TMAP_APP_KEY is not configured")

    try:
        factors = _factor_set()
    except CarbonFactorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        raw = await TmapTransitClient(app_key).routes(
            start_lon=req.start.lon,
            start_lat=req.start.lat,
            end_lon=req.end.lon,
            end_lat=req.end.lat,
            count=req.count,
            search_dttm=req.search_dttm,
        )
        routes = normalize_tmap_response(raw)
        calculate_routes_carbon(routes, factors)
        result = recommend_low_carbon_route(
            routes,
            RecommendationPolicy(
                max_time_over_fastest_pct=req.max_time_over_fastest_pct,
                max_extra_transfers=req.max_extra_transfers,
            ),
        )
        result["provider"] = "TMAP"
        result["carbon_factor_version"] = factors.version
        result["carbon_factor_source"] = factors.source
        result["carbon_boundary"] = factors.boundary
        result["production_factor_approved"] = factors.production_approved
        return result
    except (httpx.HTTPError, ValueError, CarbonFactorError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

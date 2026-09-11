from __future__ import annotations

from typing import Any

from canopy_api.models import Point, TransitLeg, TransitRoute


def _point(value: dict[str, Any] | None) -> Point | None:
    if not value:
        return None
    lon = value.get("lon")
    lat = value.get("lat")
    if lon is None or lat is None:
        return None
    return Point(lon=float(lon), lat=float(lat), name=value.get("name"))


def _geometry(leg: dict[str, Any]) -> str | None:
    pass_shape = leg.get("passShape") or {}
    if pass_shape.get("linestring"):
        return pass_shape["linestring"]

    steps = leg.get("steps") or []
    chunks = [step.get("linestring") for step in steps if step.get("linestring")]
    return " ".join(chunks) if chunks else None


def normalize_tmap_response(payload: dict[str, Any]) -> list[TransitRoute]:
    """Convert TMAP /transit/routes response to Canopy's provider-neutral route schema."""
    try:
        itineraries = payload["metaData"]["plan"]["itineraries"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid TMAP transit response: metaData.plan.itineraries is missing") from exc

    routes: list[TransitRoute] = []
    for idx, itinerary in enumerate(itineraries):
        legs: list[TransitLeg] = []
        for raw_leg in itinerary.get("legs", []):
            mode = str(raw_leg.get("mode", "OTHER")).upper()
            legs.append(
                TransitLeg(
                    mode=mode,
                    distance_m=float(raw_leg.get("distance") or 0),
                    duration_s=int(raw_leg.get("sectionTime") or 0),
                    start=_point(raw_leg.get("start")),
                    end=_point(raw_leg.get("end")),
                    route_name=raw_leg.get("route"),
                    route_id=str(raw_leg["routeId"]) if raw_leg.get("routeId") is not None else None,
                    geometry=_geometry(raw_leg),
                )
            )

        fare = itinerary.get("fare", {}).get("regular", {}).get("totalFare")
        routes.append(
            TransitRoute(
                provider="TMAP",
                provider_route_index=idx,
                total_time_s=int(itinerary.get("totalTime") or 0),
                total_distance_m=float(itinerary.get("totalDistance") or sum(x.distance_m for x in legs)),
                total_walk_distance_m=float(
                    itinerary.get("totalWalkDistance") or sum(x.distance_m for x in legs if x.mode == "WALK")
                ),
                transfer_count=int(itinerary.get("transferCount") or 0),
                fare_krw=int(fare) if fare is not None else None,
                path_type=int(itinerary["pathType"]) if itinerary.get("pathType") is not None else None,
                legs=legs,
            )
        )
    return routes

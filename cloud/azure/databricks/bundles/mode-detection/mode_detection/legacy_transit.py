"""Adapter around the preserved production transit-context implementation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contract import Observation


@lru_cache(maxsize=1)
def _runtime(reference_root: str, transit_reference_dir: str):
    """Load settings, reference tables, spatial indexes and resolver once."""

    import sys
    import pandas as pd

    root = Path(reference_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from src.transit_context.evidence import (
        bus_context,
        korail_context,
        subway_context,
    )
    from src.transit_context.resolver import resolve_mode
    from src.transit_context.settings import load_settings
    from src.transit_context.spatial import GeoPointIndex

    settings = load_settings()
    folder = Path(transit_reference_dir)

    tables: dict[str, Any] = {}
    for name in (
        "seoul_bus_stops",
        "seoul_bus_route_stops",
        "subway_stations",
        "korail_stations",
    ):
        path = folder / f"{name}.csv"
        if path.is_file():
            tables[name] = pd.read_csv(
                path,
                dtype={
                    "stop_id": str,
                    "route_id": str,
                    "station_id": str,
                    "route_no": str,
                },
            )

    indexes = {
        name: GeoPointIndex.from_frame(table)
        for name, table in tables.items()
        if name != "seoul_bus_route_stops" and len(table)
    }
    return (
        resolve_mode,
        bus_context,
        subway_context,
        korail_context,
        settings,
        tables,
        indexes,
    )


class LegacyTransitContextResolver:
    """Reuse the currently deployed bus/subway/Korail transit logic."""

    def __init__(
        self,
        *,
        reference_root: str | Path,
        transit_reference_dir: str | Path,
    ) -> None:
        self._reference_root = str(Path(reference_root))
        self._transit_reference_dir = str(Path(transit_reference_dir))

    def __call__(
        self,
        probabilities: Mapping[str, float],
        observations: Sequence[Observation],
        station_history: Sequence[tuple[str, str]],
    ):
        (
            resolve_mode,
            bus_context,
            subway_context,
            korail_context,
            settings,
            tables,
            indexes,
        ) = _runtime(self._reference_root, self._transit_reference_dir)

        context: dict[str, Any] = {
            "bus_applicability": "INSUFFICIENT_REFERENCE",
            "rail_applicability": "INSUFFICIENT_REFERENCE",
            "transit_applicability": "INSUFFICIENT_REFERENCE",
            "context_status": "INSUFFICIENT_REFERENCE",
        }

        if len(observations) < 2:
            return resolve_mode(
                probabilities,
                context=context,
                settings=settings,
            ), context

        coordinates = [(point.lat, point.lon) for point in observations]
        common = {
            "start_latitude": observations[0].lat,
            "start_longitude": observations[0].lon,
            "end_latitude": observations[-1].lat,
            "end_longitude": observations[-1].lon,
            "settings": settings,
        }

        if "seoul_bus_stops" in indexes:
            index = indexes["seoul_bus_stops"]
            nearest = index.nearest_many(coordinates)
            observed: list[str] = []
            for _, row in nearest.iterrows():
                if (
                    row["distance_m"] <= settings.radii_m["bus_stop"]
                    and (not observed or observed[-1] != str(row["stop_id"]))
                ):
                    observed.append(str(row["stop_id"]))

            context.update(
                bus_context(
                    **common,
                    bus_stop_index=index,
                    bus_stops=tables["seoul_bus_stops"],
                    bus_route_stops=tables.get("seoul_bus_route_stops"),
                    observed_stop_ids=observed,
                )
            )
            context["bus_applicability"] = (
                "APPLICABLE"
                if nearest["distance_m"].min() <= 5000
                else "NOT_APPLICABLE"
            )

        rail_applicability: list[str] = []

        if "subway_stations" in indexes:
            index = indexes["subway_stations"]
            context.update(
                subway_context(
                    **common,
                    station_index=index,
                    stations=tables["subway_stations"],
                    ml_rail_probability=float(probabilities.get("rail", 0.0)),
                    trajectory=coordinates,
                    station_history=station_history,
                )
            )
            rail_applicability.append(
                "APPLICABLE"
                if index.nearest_many(coordinates)["distance_m"].min() <= 5000
                else "NOT_APPLICABLE"
            )

        if "korail_stations" in indexes:
            index = indexes["korail_stations"]
            context.update(
                korail_context(
                    **common,
                    station_index=index,
                    ml_rail_probability=float(probabilities.get("rail", 0.0)),
                )
            )
            rail_applicability.append(
                "APPLICABLE"
                if index.nearest_many(coordinates)["distance_m"].min() <= 20000
                else "NOT_APPLICABLE"
            )

        if rail_applicability:
            context["rail_applicability"] = (
                "APPLICABLE"
                if "APPLICABLE" in rail_applicability
                else "NOT_APPLICABLE"
            )

        if indexes:
            context["context_status"] = (
                "READY"
                if len(indexes) == 3 and "seoul_bus_route_stops" in tables
                else "PARTIAL_REFERENCE"
            )
            context["transit_applicability"] = (
                "APPLICABLE"
                if "APPLICABLE"
                in (
                    context["bus_applicability"],
                    context["rail_applicability"],
                )
                else "NOT_APPLICABLE"
            )

        decision = resolve_mode(
            probabilities,
            context=context,
            settings=settings,
        )

        # Preserve current production semantics: missing reference data is not
        # evidence that the ML prediction is wrong.
        if not indexes:
            mode = max(probabilities, key=probabilities.get)
            decision.update(
                final_mode=mode,
                decision_confidence=float(probabilities[mode]),
                correction_applied=False,
                decision_status="insufficient_reference",
                correction_reason=(
                    "Transit reference data is not installed; ML-only result"
                ),
            )

        return decision, context

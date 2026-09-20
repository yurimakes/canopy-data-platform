"""Deployment-owned Unity Catalog names for generic Canopy ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_SCHEMAS = {"default", "information_schema"}


@dataclass(frozen=True)
class EventIngestionTableConfig:
    """Build canonical Bronze and Silver table names."""

    catalog: str = "dbw_canopy_trial"
    bronze_schema: str = "bronze"
    silver_schema: str = "silver"
    bronze_events_name: str = "events"
    gps_observations_name: str = "gps_observations"
    gps_quarantine_name: str = "gps_quarantine"
    trip_ended_events_name: str = "trip_ended_events"

    def __post_init__(self) -> None:
        values = (
            self.catalog,
            self.bronze_schema,
            self.silver_schema,
            self.bronze_events_name,
            self.gps_observations_name,
            self.gps_quarantine_name,
            self.trip_ended_events_name,
        )
        for value in values:
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid Unity Catalog identifier: {value!r}")
        for schema in (self.bronze_schema, self.silver_schema):
            if schema.lower() in _RESERVED_SCHEMAS:
                raise ValueError(f"pipeline schema cannot be {schema!r}")

    @property
    def bronze_table(self) -> str:
        return f"{self.catalog}.{self.bronze_schema}.{self.bronze_events_name}"

    @property
    def observations_table(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.gps_observations_name}"

    @property
    def quarantine_table(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.gps_quarantine_name}"

    @property
    def trip_ended_events_table(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.trip_ended_events_name}"

"""Deployment-owned Unity Catalog names for generic Canopy ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_SCHEMAS = {"default", "information_schema"}


@dataclass(frozen=True)
class EventIngestionTableConfig:
    """Build sandbox table names while preserving intended medallion hierarchy."""

    catalog: str = "dbw_canopy_trial"
    schema: str = "sandbox"
    bronze_events_name: str = "bronze_events"
    gps_observations_name: str = "silver_gps_observations"
    gps_quarantine_name: str = "silver_gps_quarantine"
    trip_ended_events_name: str = "silver_trip_ended_events"

    def __post_init__(self) -> None:
        values = (
            self.catalog,
            self.schema,
            self.bronze_events_name,
            self.gps_observations_name,
            self.gps_quarantine_name,
            self.trip_ended_events_name,
        )
        for value in values:
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid Unity Catalog identifier: {value!r}")
        if self.schema.lower() in _RESERVED_SCHEMAS:
            raise ValueError(f"pipeline schema cannot be {self.schema!r}")

    @property
    def bronze_table(self) -> str:
        return self._table(self.bronze_events_name)

    @property
    def observations_table(self) -> str:
        return self._table(self.gps_observations_name)

    @property
    def quarantine_table(self) -> str:
        return self._table(self.gps_quarantine_name)

    @property
    def trip_ended_events_table(self) -> str:
        return self._table(self.trip_ended_events_name)

    def _table(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"

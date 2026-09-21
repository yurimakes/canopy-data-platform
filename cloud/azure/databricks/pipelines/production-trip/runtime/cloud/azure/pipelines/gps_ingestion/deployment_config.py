"""Deployment-owned Unity Catalog names for GPS ingestion Pipeline A."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_SCHEMAS = {"default", "information_schema"}


@dataclass(frozen=True)
class GpsIngestionTableConfig:
    """Build the three Pipeline A table names without using ``default``.

    The development defaults match the verified ``dbw-canopy-dev`` workspace.
    Every value can be replaced by an Asset Bundle target or pipeline setting.
    """

    catalog: str = "dbw_canopy_dev"
    bronze_schema: str = "bronze"
    silver_schema: str = "silver"
    bronze_events_name: str = "gps_events"
    observations_name: str = "gps_observations"
    quarantine_name: str = "gps_quarantine"

    def __post_init__(self) -> None:
        values = (
            self.catalog,
            self.bronze_schema,
            self.silver_schema,
            self.bronze_events_name,
            self.observations_name,
            self.quarantine_name,
        )
        for value in values:
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid Unity Catalog identifier: {value!r}")
        schemas = (self.bronze_schema, self.silver_schema)
        for schema in schemas:
            if schema.lower() in _RESERVED_SCHEMAS:
                raise ValueError(f"pipeline schema cannot be {schema!r}")
        if len(set(schemas)) != len(schemas):
            raise ValueError("bronze and silver schemas must be distinct")

    @property
    def bronze_table(self) -> str:
        return self._table(self.bronze_schema, self.bronze_events_name)

    @property
    def observations_table(self) -> str:
        return self._table(self.silver_schema, self.observations_name)

    @property
    def quarantine_table(self) -> str:
        return self._table(self.silver_schema, self.quarantine_name)

    def _table(self, schema: str, name: str) -> str:
        return f"{self.catalog}.{schema}.{name}"

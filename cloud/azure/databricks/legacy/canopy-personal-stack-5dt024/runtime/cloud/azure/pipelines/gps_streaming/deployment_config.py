"""Deployment-owned Unity Catalog names for the GPS streaming pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_SCHEMAS = {"default", "information_schema"}


@dataclass(frozen=True)
class CanopyTableConfig:
    """Build three-part object names without falling back to ``default``.

    The development defaults match the verified ``dbw-canopy-dev`` workspace.
    Every value can be replaced by an Asset Bundle target or pipeline setting.
    """

    catalog: str = "dbw_canopy_dev"
    bronze_schema: str = "bronze"
    silver_schema: str = "silver"
    gold_schema: str = "gold"
    ml_schema: str = "ml"
    bronze_events_name: str = "gps_events"
    observations_name: str = "gps_observations"
    quarantine_name: str = "gps_quarantine"
    features_name: str = "gps_features"
    segments_name: str = "mode_segments"
    predictions_name: str = "mode_segment_predictions"

    def __post_init__(self) -> None:
        values = (
            self.catalog,
            self.bronze_schema,
            self.silver_schema,
            self.gold_schema,
            self.ml_schema,
            self.bronze_events_name,
            self.observations_name,
            self.quarantine_name,
            self.features_name,
            self.segments_name,
            self.predictions_name,
        )
        for value in values:
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid Unity Catalog identifier: {value!r}")
        schemas = (
            self.bronze_schema,
            self.silver_schema,
            self.gold_schema,
            self.ml_schema,
        )
        for schema in schemas:
            if schema.lower() in _RESERVED_SCHEMAS:
                raise ValueError(f"pipeline schema cannot be {schema!r}")
        if len(set(schemas)) != len(schemas):
            raise ValueError("bronze, silver, gold, and ml schemas must be distinct")

    @property
    def bronze_table(self) -> str:
        return self._table(self.bronze_schema, self.bronze_events_name)

    @property
    def observations_table(self) -> str:
        return self._table(self.silver_schema, self.observations_name)

    @property
    def quarantine_table(self) -> str:
        return self._table(self.silver_schema, self.quarantine_name)

    @property
    def features_table(self) -> str:
        return self._table(self.silver_schema, self.features_name)

    @property
    def segments_table(self) -> str:
        return self._table(self.silver_schema, self.segments_name)

    @property
    def predictions_table(self) -> str:
        return self._table(self.gold_schema, self.predictions_name)

    def _table(self, schema: str, name: str) -> str:
        return f"{self.catalog}.{schema}.{name}"

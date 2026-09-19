import dataclasses
import unittest

from gps_ingestion.deployment_config import EventIngestionTableConfig


class EventIngestionTableConfigTest(unittest.TestCase):
    def test_defaults_expose_sandbox_medallion_intent(self) -> None:
        tables = EventIngestionTableConfig()
        self.assertEqual(
            {
                tables.bronze_table,
                tables.observations_table,
                tables.quarantine_table,
                tables.trip_ended_events_table,
            },
            {
                "dbw_canopy_trial.sandbox.bronze_events",
                "dbw_canopy_trial.sandbox.silver_gps_observations",
                "dbw_canopy_trial.sandbox.silver_gps_quarantine",
                "dbw_canopy_trial.sandbox.silver_trip_ended_events",
            },
        )
        self.assertEqual(
            {field.name for field in dataclasses.fields(tables)},
            {
                "catalog",
                "schema",
                "bronze_events_name",
                "gps_observations_name",
                "gps_quarantine_name",
                "trip_ended_events_name",
            },
        )

    def test_invalid_identifier_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid Unity Catalog identifier"):
            EventIngestionTableConfig(catalog="not-valid")

    def test_reserved_schema_is_rejected(self) -> None:
        for value in ("default", "information_schema"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "cannot be"):
                EventIngestionTableConfig(schema=value)


if __name__ == "__main__":
    unittest.main()

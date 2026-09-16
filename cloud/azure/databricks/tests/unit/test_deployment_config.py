import dataclasses
import unittest

from gps_ingestion.deployment_config import GpsIngestionTableConfig


class GpsIngestionTableConfigTest(unittest.TestCase):
    def test_defaults_expose_exactly_three_owned_public_tables(self) -> None:
        tables = GpsIngestionTableConfig()
        self.assertEqual(
            {
                tables.bronze_table,
                tables.observations_table,
                tables.quarantine_table,
            },
            {
                "dbw_canopy_dev.bronze.gps_events",
                "dbw_canopy_dev.silver.gps_observations",
                "dbw_canopy_dev.silver.gps_quarantine",
            },
        )
        self.assertEqual(
            {field.name for field in dataclasses.fields(tables)},
            {
                "catalog",
                "bronze_schema",
                "silver_schema",
                "bronze_events_name",
                "observations_name",
                "quarantine_name",
            },
        )

    def test_invalid_identifier_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid Unity Catalog identifier"):
            GpsIngestionTableConfig(catalog="not-valid")

    def test_reserved_schemas_are_rejected(self) -> None:
        for value in ("default", "information_schema"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "cannot be"):
                GpsIngestionTableConfig(silver_schema=value)

    def test_bronze_and_silver_must_be_distinct(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            GpsIngestionTableConfig(silver_schema="bronze")


if __name__ == "__main__":
    unittest.main()

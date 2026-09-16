import unittest

from gps_ingestion.deployment_config import CanopyTableConfig


class CanopyTableConfigTest(unittest.TestCase):
    def test_development_defaults_use_dedicated_project_schemas(self) -> None:
        tables = CanopyTableConfig()
        self.assertEqual(tables.bronze_table, "dbw_canopy_dev.bronze.gps_events")
        self.assertEqual(tables.features_table, "dbw_canopy_dev.silver.gps_features")
        self.assertEqual(tables.predictions_table, "dbw_canopy_dev.gold.mode_segment_predictions")
        self.assertEqual(tables.ml_schema, "ml")

    def test_all_names_are_deployment_configurable(self) -> None:
        tables = CanopyTableConfig(
            catalog="canopy_prod",
            bronze_schema="raw",
            silver_schema="refined",
            gold_schema="serving",
            ml_schema="models",
            features_name="trip_features",
        )
        self.assertEqual(tables.features_table, "canopy_prod.refined.trip_features")
        self.assertEqual(tables.ml_schema, "models")

    def test_default_and_reused_schemas_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be"):
            CanopyTableConfig(bronze_schema="default")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            CanopyTableConfig(gold_schema="silver")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            CanopyTableConfig(ml_schema="gold")


if __name__ == "__main__":
    unittest.main()

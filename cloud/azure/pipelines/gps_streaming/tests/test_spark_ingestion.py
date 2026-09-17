import unittest

from cloud.azure.pipelines.gps_streaming.deployment_config import CanopyTableConfig
from cloud.azure.pipelines.gps_streaming.spark_ingestion import (
    SparkIngestionConfig,
    table_ddl,
)


def config(**overrides) -> SparkIngestionConfig:
    values = {
        "bronze_checkpoint": "abfss://checkpoints/gps-bronze",
        "observations_checkpoint": "abfss://checkpoints/gps-observations",
        "quarantine_checkpoint": "abfss://checkpoints/gps-quarantine",
    }
    values.update(overrides)
    return SparkIngestionConfig(**values)


class SparkIngestionConfigTest(unittest.TestCase):
    def test_requires_workspace_checkpoint_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            config(bronze_checkpoint="")

    def test_rejects_default_pipeline_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be"):
            config(tables=CanopyTableConfig(silver_schema="default"))

    def test_ddl_contains_all_pipeline_owned_tables_and_contract_fields(self) -> None:
        statements = "\n".join(table_ddl(config()))
        for table in (
            "dbw_canopy_dev.bronze.gps_events",
            "dbw_canopy_dev.silver.gps_observations",
            "dbw_canopy_dev.silver.gps_quarantine",
            "dbw_canopy_dev.silver.gps_features",
            "dbw_canopy_dev.silver.mode_segments",
        ):
            self.assertIn(table, statements)
        for field in (
            "raw_speed DOUBLE",
            "derived_speed_kmh DOUBLE",
            "speed_min_60s DOUBLE",
            "detector_version STRING",
        ):
            self.assertIn(field, statements)


if __name__ == "__main__":
    unittest.main()

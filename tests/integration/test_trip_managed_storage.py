"""저장 대상 검증과 잘못된 외부 테이블 연결 방지."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import sys
import json
import tempfile
import unittest
import zipfile
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud/azure/pipelines/databricks"))
import trip_delta_store as storage


class ManagedStorageTests(unittest.TestCase):
    def test_rejects_paths_and_sql_as_table_names(self):
        for value in ("gold.trips", "abfss://container/path", "a.b.c; DROP TABLE a.b.c", "a.b.c.d", "a.`b`.c"):
            with self.assertRaises(ValueError):
                storage.table_name(value)
        self.assertEqual(storage.table_name("canopy.sandbox.final_trips"), "canopy.sandbox.final_trips")

    def test_mock_requires_explicit_test_schema(self):
        self.assertTrue(storage.test_target("canopy.sandbox.final_trips"))
        self.assertFalse(storage.test_target("canopy.gold.final_trips"))
        self.assertTrue(storage.test_target("abfss://curated@a/pipeline_test/final_trips"))
        self.assertFalse(storage.test_target("abfss://curated@a/gold/final_trips"))

    def test_named_external_table_is_not_a_managed_migration(self):
        spark = Mock()
        for kind, provider in (("EXTERNAL", "delta"), ("MANAGED", "parquet"), ("VIEW", "delta")):
            spark.sql.return_value.collect.return_value = [SimpleNamespace(col_name="Type", data_type=kind), SimpleNamespace(col_name="Provider", data_type=provider)]
            with self.assertRaises(ValueError):
                storage.assert_managed_delta(spark, "canopy.sandbox.final_trips")

    def test_existing_managed_table_is_not_overwritten(self):
        spark, frame = Mock(), Mock()
        spark.catalog.tableExists.return_value = True
        spark.sql.return_value.collect.return_value = [SimpleNamespace(col_name="Type", data_type="MANAGED"), SimpleNamespace(col_name="Provider", data_type="delta")]
        storage.initialize(spark, "canopy.sandbox.final_trips", frame)
        frame.limit.return_value.write.format.return_value.mode.return_value.saveAsTable.assert_not_called()

    def test_cli_selects_only_one_storage_target(self):
        parser = argparse.ArgumentParser()
        storage.add_target(parser, "gold")
        args = parser.parse_args(["--gold-table", "canopy.sandbox.final_trips"])
        self.assertEqual(storage.target_arg(args, "gold"), "canopy.sandbox.final_trips")
        with self.assertRaises(SystemExit):
            parser.parse_args(["--gold-table", "canopy.sandbox.final_trips", "--gold-path", "/old"])

    def test_phone_package_contains_managed_targets_and_storage_module(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/azure"))
        from package_trip_pipeline import package
        with tempfile.TemporaryDirectory() as directory:
            path = package(Path(directory) / "trip.zip", "/Workspace/test", None,
                "https://example.documents.azure.com", "scope", "key", iphone=True,
                gold_table="canopy.sandbox.final_trips", queue_table="canopy.sandbox.trip_wait")
            with zipfile.ZipFile(path) as archive:
                job = json.loads(archive.read("trip_finalization_job.json"))
                parameters = job["tasks"][0]["spark_python_task"]["parameters"]
                self.assertIn("--gold-table", parameters)
                self.assertIn("--queue-table", parameters)
                self.assertNotIn("--gold-path", parameters)
                self.assertIn("cloud/azure/pipelines/databricks/trip_delta_store.py", archive.namelist())


if __name__ == "__main__":
    unittest.main()

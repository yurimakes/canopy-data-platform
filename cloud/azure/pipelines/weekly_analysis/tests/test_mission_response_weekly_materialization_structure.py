"""Static integration checks for Mission Response weekly materialization."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
TARGET = (
    ROOT
    / "cloud"
    / "azure"
    / "pipelines"
    / "databricks"
    / "materialize_mission_response_weekly.py"
)


class MissionResponseWeeklyMaterializationStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TARGET.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_reads_frozen_bundle_and_uses_existing_cores(self):
        self.assertIn("type = 'mission_bundle'", self.source)
        self.assertIn("build_progress_rows", self.source)
        self.assertIn("build_response_rows", self.source)
        self.assertIn("completion_rule", self.source)

    def test_does_not_issue_new_bundle_or_use_behavior_change(self):
        self.assertNotIn("issue_weekly_bundle(", self.source)
        self.assertIn('"mission_bundle_issued_here": False', self.source)
        self.assertIn('"behavior_change_used": False', self.source)

    def test_uses_serverless_service_credential(self):
        self.assertIn(
            "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME",
            self.source,
        )
        self.assertIn(
            "getServiceCredentialsProvider",
            self.source,
        )
        self.assertNotIn("DefaultAzureCredential", self.source)

    def test_writes_partitioned_mission_response_gold(self):
        self.assertIn(
            "CANOPY_GOLD_MISSION_RESPONSE_PATH",
            self.source,
        )
        self.assertIn(
            '.partitionBy("campaign_id", "week_start")',
            self.source,
        )
        self.assertIn(
            '"replaceWhere"',
            self.source,
        )

    def test_no_issued_bundle_is_an_explicit_zero_row_no_op(self):
        run = next(
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        branch = next(
            node for node in ast.walk(run)
            if isinstance(node, ast.If) and ast.unparse(node.test) == "not bundles"
        )
        branch_source = ast.get_source_segment(self.source, branch)
        self.assertIn('"status": "NO_ISSUED_BUNDLE"', branch_source)
        self.assertIn('"issued_assignment_count": 0', branch_source)
        self.assertIn('"final_trip_rows_read": 0', branch_source)
        self.assertIn('"progress_rows": 0', branch_source)
        self.assertIn('"partition_write_performed": False', branch_source)
        self.assertIn('"existing_partition_preserved": True', branch_source)
        self.assertNotIn("_write_response_partition", branch_source)
        self.assertNotIn("_verify_response_partition", branch_source)
        self.assertNotIn("replaceWhere", branch_source)
        read_source = self._function_source("_read_issued_bundles")
        self.assertNotIn("No issued Mission Bundle found", read_source)

    def _function_source(self, name):
        function = next(
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return ast.get_source_segment(self.source, function)

    def test_final_trip_default_matches_weekly_pipeline_dev_input(self):
        self.assertIn(
            'DEFAULT_FINAL_TRIP_TABLE = "dbw_canopy_dev.sandbox.final_trips"',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()

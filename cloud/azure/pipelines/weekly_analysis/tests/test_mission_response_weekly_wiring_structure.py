import ast
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT.parent
MATERIALIZER = PIPELINES / "databricks" / "materialize_mission_response_weekly.py"
PROGRESS = PIPELINES / "databricks" / "mission_progress.py"
RESPONSE = PIPELINES / "databricks" / "build_mission_response.py"
BUNDLE = ROOT / "databricks.yml"


def function(tree, name):
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def function_source(source, tree, name):
    return ast.get_source_segment(source, function(tree, name))


def isolated_function(tree, name, namespace):
    module = ast.Module(body=[function(tree, name)], type_ignores=[])
    exec(compile(module, str(MATERIALIZER), "exec"), namespace)
    return namespace[name]


class MissionResponseWeeklyWiringStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MATERIALIZER.read_text(encoding="utf-8")
        cls.progress_source = PROGRESS.read_text(encoding="utf-8")
        cls.response_source = RESPONSE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.bundle = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
        cls.job = cls.bundle["resources"]["jobs"]["weekly_analysis_job"]
        cls.tasks = {task["task_key"]: task for task in cls.job["tasks"]}

    def test_iso_week_is_monday_to_next_monday_exclusive(self):
        bounds = isolated_function(
            self.tree,
            "_iso_week_bounds",
            {"datetime": datetime, "timedelta": timedelta},
        )
        self.assertEqual(bounds("2026-W38"), ("2026-09-14", "2026-09-21"))
        with self.assertRaisesRegex(ValueError, "ISO"):
            bounds("2026-09-14")

    def test_cli_and_environment_service_credential_priority(self):
        resolve = isolated_function(
            self.tree,
            "_service_credential_name",
            {
                "os": os,
                "SERVICE_CREDENTIAL_ENV": (
                    "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME"
                ),
            },
        )
        with patch.dict(
            os.environ,
            {"CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME": "from-env"},
            clear=False,
        ):
            self.assertEqual(resolve("from-cli"), "from-cli")
            self.assertEqual(resolve(None), "from-env")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "required"):
                resolve(None)

    def test_cli_and_environment_mission_container_priority_without_default(self):
        resolve = isolated_function(
            self.tree,
            "_mission_container_name",
            {"os": os},
        )
        with patch.dict(
            os.environ,
            {"CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER": "from-env"},
            clear=False,
        ):
            self.assertEqual(resolve("from-cli"), "from-cli")
            self.assertEqual(resolve(None), "from-env")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Mission container required"):
                resolve(None)
        self.assertNotIn("mission-state", self.source)
        self.assertNotIn("mission-assignments", self.source)

    def test_cli_has_explicit_campaign_week_and_optional_runtime_config(self):
        source = function_source(self.source, self.tree, "parse_args")
        self.assertIn('"--campaign-id", required=True', source)
        self.assertIn('"--week", required=True', source)
        self.assertIn('"--service-credential-name"', source)
        self.assertIn('"--endpoint"', source)
        self.assertIn('"--mission-container"', source)

    def test_existing_progress_and_response_cores_remain_the_only_builders(self):
        run_source = function_source(self.source, self.tree, "run")
        self.assertIn("from mission_progress import build_progress_rows", run_source)
        self.assertIn("from build_mission_response import build_response_rows", run_source)
        self.assertNotIn("mission_policy", run_source)
        self.assertNotIn("build_behavior_change", run_source)
        self.assertNotIn('spark.read.table("behavior_change")', run_source)
        self.assertIn('assignment.get("completion_rule")', self.progress_source)

    def test_incomplete_assignments_remain_zero_progress_responses(self):
        self.assertIn('p.get("progress_count", 0)', self.response_source)
        self.assertIn('p.get("achievement_rate", 0.0)', self.response_source)
        self.assertIn('p.get("completed", False)', self.response_source)
        self.assertIn('p.get("qualified_trip_ids", [])', self.response_source)

    def test_same_scope_rerun_replaces_one_partition(self):
        source = function_source(
            self.source,
            self.tree,
            "_write_response_partition",
        )
        self.assertIn('.option(\n            "replaceWhere"', source)
        self.assertIn("campaign_id = '", source)
        self.assertIn("week_start = '", source)
        self.assertIn('.partitionBy("campaign_id", "week_start")', source)

    def test_no_bundle_preserves_scope_without_any_delta_write(self):
        run = function(self.tree, "run")
        branch = next(
            node for node in ast.walk(run)
            if isinstance(node, ast.If) and ast.unparse(node.test) == "not bundles"
        )
        no_bundle = ast.get_source_segment(self.source, branch)
        self.assertIn('"status": "NO_ISSUED_BUNDLE"', no_bundle)
        self.assertIn('"partition_write_performed": False', no_bundle)
        self.assertIn('"existing_partition_preserved": True', no_bundle)
        self.assertNotIn("_write_response_partition", no_bundle)
        self.assertNotIn("_verify_response_partition", no_bundle)
        self.assertNotIn("replaceWhere", no_bundle)

    def test_no_credential_or_secret_value_is_logged(self):
        run_source = function_source(self.source, self.tree, "run")
        self.assertNotIn("print(credential", self.source)
        self.assertNotIn("print(service_credential", self.source)
        self.assertNotIn('"service_credential_name":', run_source)
        self.assertNotIn('"credential":', run_source)
        self.assertNotIn('"token":', run_source)

    def test_bundle_sync_includes_weekly_and_sibling_databricks_sources(self):
        self.assertEqual(self.bundle["sync"]["paths"], [".", "../databricks"])
        self.assertIn("**/.pytest_cache/**", self.bundle["sync"]["exclude"])
        pipeline = self.bundle["resources"]["pipelines"][
            "weekly_analysis_pipeline"
        ]
        self.assertEqual(
            pipeline["libraries"][0]["file"]["path"],
            "${workspace.file_path}/weekly_analysis/weekly_pipeline.py",
        )
        self.assertEqual(
            self.tasks["materialize_mission_response_weekly"][
                "spark_python_task"
            ]["python_file"],
            "${workspace.file_path}/databricks/materialize_mission_response_weekly.py",
        )

    def test_job_task_order_and_dependencies(self):
        self.assertEqual(
            [task["task_key"] for task in self.job["tasks"]],
            [
                "materialize_mission_response_weekly",
                "run_weekly_pipeline",
                "publish_reward_ledger",
                "refresh_weekly_after_reward",
                "publish_weekly_cosmos",
            ],
        )
        self.assertEqual(
            self.tasks["run_weekly_pipeline"]["depends_on"],
            [{"task_key": "materialize_mission_response_weekly"}],
        )
        self.assertEqual(
            self.tasks["publish_reward_ledger"]["depends_on"],
            [{"task_key": "run_weekly_pipeline"}],
        )

    def test_mission_task_uses_job_scope_variable_and_cosmos_dependency(self):
        mission_task = self.tasks["materialize_mission_response_weekly"]
        parameters = mission_task["spark_python_task"]["parameters"]
        self.assertIn("{{job.parameters.campaign_id}}", parameters)
        self.assertIn("{{job.parameters.week}}", parameters)
        self.assertIn("${var.mission_service_credential_name}", parameters)
        self.assertIn("--mission-container", parameters)
        self.assertIn("${var.mission_container_name}", parameters)
        self.assertEqual(
            self.bundle["variables"]["mission_service_credential_name"]["default"],
            "",
        )
        self.assertEqual(
            self.bundle["variables"]["mission_container_name"]["default"],
            "",
        )
        environments = {
            environment["environment_key"]: environment["spec"]
            for environment in self.job["environments"]
        }
        self.assertEqual(
            environments["mission_response_materialization"]["dependencies"],
            ["azure-cosmos==4.17.0"],
        )


if __name__ == "__main__":
    unittest.main()

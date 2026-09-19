"""Structure checks for canonical weekly Mission Profile integration."""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import types
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT.parent
MATERIALIZER = PIPELINES / "databricks" / "materialize_mission_profile_weekly.py"
CORE = PIPELINES / "databricks" / "build_mission_profile.py"
HELPER = ROOT / "helpers" / "weekly_user_profile.py"
PIPELINE = ROOT / "weekly_pipeline.py"
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


def load_materializer():
    spec = importlib.util.spec_from_file_location(
        "mission_profile_weekly_materializer_test",
        MATERIALIZER,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_modules(profile_builder):
    spark = types.SimpleNamespace(
        conf=types.SimpleNamespace(set=lambda *args: None),
    )
    spark_session = types.SimpleNamespace(
        builder=types.SimpleNamespace(getOrCreate=lambda: spark),
    )
    pyspark = types.ModuleType("pyspark")
    pyspark_sql = types.ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = spark_session
    pyspark.sql = pyspark_sql

    core = types.ModuleType("build_mission_profile")
    core._gold_profile = lambda profile: dict(profile)
    core._responses_to_bundles = lambda rows: list(rows)
    core.build_profile_from_weekly_summary = profile_builder
    return spark, {
        "pyspark": pyspark,
        "pyspark.sql": pyspark_sql,
        "build_mission_profile": core,
    }


class MissionProfileWeeklyIntegrationStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MATERIALIZER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.core_source = CORE.read_text(encoding="utf-8")
        cls.helper_source = HELPER.read_text(encoding="utf-8")
        cls.helper_tree = ast.parse(cls.helper_source)
        cls.pipeline_source = PIPELINE.read_text(encoding="utf-8")
        cls.pipeline_tree = ast.parse(cls.pipeline_source)
        cls.bundle = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
        cls.job = cls.bundle["resources"]["jobs"]["weekly_analysis_job"]
        cls.tasks = {task["task_key"]: task for task in cls.job["tasks"]}

    def test_reuses_profile_core_without_copying_policy(self):
        run = function_source(self.source, self.tree, "run")
        self.assertIn("build_profile_from_weekly_summary", run)
        self.assertIn("_responses_to_bundles", run)
        self.assertIn("_gold_profile", run)
        self.assertIn("_latest_profile_document", self.source)
        for name in (
            "compute_category_preferences",
            "compute_difficulty_state",
            "compute_family_capability",
        ):
            self.assertIn(f"def {name}", self.core_source)
            self.assertNotIn(f"def {name}", self.source)
        self.assertNotIn("mission_policy", self.source)

    def test_iso_week_uses_monday_to_next_monday(self):
        bounds = isolated_function(
            self.tree,
            "_iso_week_bounds",
            {"datetime": datetime, "timedelta": timedelta},
        )
        self.assertEqual(bounds("2026-W38"), ("2026-09-14", "2026-09-21"))
        with self.assertRaisesRegex(ValueError, "ISO"):
            bounds("2026-09-14")

    def test_weekly_source_supports_managed_table(self):
        source = function_source(self.source, self.tree, "_read_weekly_source")
        self.assertIn('source.startswith("table:")', source)
        self.assertIn("spark.table(table_name)", source)
        self.assertIn('spark.read.format("delta").load(source)', source)

    def test_response_gold_history_is_scoped_without_cosmos_fallback(self):
        source = function_source(
            self.source,
            self.tree,
            "_response_history_by_user",
        )
        self.assertIn("CANOPY_GOLD_MISSION_RESPONSE_PATH", source)
        self.assertIn('F.col("campaign_id") == campaign_id', source)
        self.assertIn('F.col("week_start") <= source_week_start', source)
        self.assertIn('"PATH_NOT_FOUND"', source)
        self.assertNotIn("query_items", source)
        self.assertNotIn("cosmos_bundle_fallback", self.source)
        self.assertNotIn("behavior_change", self.source.lower())

    def test_profile_partition_is_deterministic_and_zero_rows_preserve_it(self):
        write = function_source(
            self.source,
            self.tree,
            "_write_profile_partition",
        )
        self.assertIn('"replaceWhere"', write)
        self.assertIn("campaign_id = '", write)
        self.assertIn("source_week_start = '", write)
        self.assertIn('.partitionBy("campaign_id", "source_week_start")', write)

        run = function(self.tree, "run")
        branch = next(
            node for node in ast.walk(run)
            if isinstance(node, ast.If) and ast.unparse(node.test) == "not profiles"
        )
        no_rows = ast.get_source_segment(self.source, branch)
        self.assertIn('"status": "NO_PROFILE_ROWS"', no_rows)
        self.assertIn('"partition_write_performed": False', no_rows)
        self.assertIn('"existing_partition_preserved": True', no_rows)
        self.assertNotIn("_write_profile_partition", no_rows)
        self.assertNotIn("_upsert_latest_profiles", no_rows)

        run_source = ast.get_source_segment(self.source, run)
        no_rows_index = run_source.index("if not profiles:")
        self.assertLess(no_rows_index, run_source.index("_service_credential_name("))
        self.assertLess(no_rows_index, run_source.index("_profile_container_name("))
        self.assertLess(no_rows_index, run_source.index("_cosmos_endpoint("))

    def test_zero_profiles_need_no_cosmos_runtime_configuration(self):
        materializer = load_materializer()
        _, modules = runtime_modules(lambda *args, **kwargs: None)

        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(
                patch.object(
                    materializer,
                    "_weekly_summary_maps",
                    return_value=({}, {}),
                )
            )
            stack.enter_context(
                patch.object(
                    materializer,
                    "_response_history_by_user",
                    return_value={},
                )
            )
            for name in (
                "_service_credential_name",
                "_profile_container_name",
                "_cosmos_endpoint",
                "_profile_container",
                "_write_profile_partition",
                "_upsert_latest_profiles",
            ):
                stack.enter_context(
                    patch.object(
                        materializer,
                        name,
                        side_effect=AssertionError(f"unexpected call: {name}"),
                    )
                )

            result = materializer.run(
                "campaign-1",
                "2026-09-14",
                "2026-09-21",
                weekly_source="table:catalog.schema.weekly_gold",
            )

        self.assertEqual(result["status"], "NO_PROFILE_ROWS")
        self.assertFalse(result["partition_write_performed"])
        self.assertTrue(result["existing_partition_preserved"])
        self.assertEqual(result["cosmos_upsert_count"], 0)

    def test_profiles_require_each_cosmos_runtime_setting(self):
        def profile_builder(*args, **kwargs):
            return {
                "user_id": kwargs["user_id"],
                "campaign_id": kwargs["campaign_id"],
                "mission_history_source": kwargs["mission_history_source"],
            }

        cases = (
            ({}, "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME"),
            ({"service_credential_name": "credential"}, "Profile container"),
            (
                {
                    "service_credential_name": "credential",
                    "profile_container": "profile-container",
                },
                "Cosmos endpoint",
            ),
        )

        for runtime_args, message in cases:
            with self.subTest(message=message):
                materializer = load_materializer()
                _, modules = runtime_modules(profile_builder)
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(sys.modules, modules))
                    stack.enter_context(patch.dict(os.environ, {}, clear=True))
                    stack.enter_context(
                        patch.object(
                            materializer,
                            "_weekly_summary_maps",
                            return_value=({"user-1": {}}, {"user-1": None}),
                        )
                    )
                    stack.enter_context(
                        patch.object(
                            materializer,
                            "_response_history_by_user",
                            return_value={},
                        )
                    )
                    write = stack.enter_context(
                        patch.object(materializer, "_write_profile_partition")
                    )
                    with self.assertRaisesRegex(RuntimeError, message):
                        materializer.run(
                            "campaign-1",
                            "2026-09-14",
                            "2026-09-21",
                            weekly_source="table:catalog.schema.weekly_gold",
                            **runtime_args,
                        )
                    write.assert_not_called()

    def test_gold_write_precedes_cosmos_latest_upsert(self):
        run = function_source(self.source, self.tree, "run")
        self.assertLess(
            run.index("_write_profile_partition("),
            run.index("_upsert_latest_profiles("),
        )
        self.assertIn("_latest_profile_document(profile)", self.source)
        self.assertIn("getServiceCredentialsProvider", self.source)
        self.assertNotIn("DefaultAzureCredential", self.source)
        self.assertNotIn(
            '"mission_history_source": "mission_response_gold"',
            run,
        )

    def test_runtime_credential_and_profile_container_have_no_default(self):
        resolve_credential = isolated_function(
            self.tree,
            "_service_credential_name",
            {
                "os": os,
                "SERVICE_CREDENTIAL_ENV": "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME",
            },
        )
        resolve_container = isolated_function(
            self.tree,
            "_profile_container_name",
            {
                "os": os,
                "PROFILE_CONTAINER_ENV": "CANOPY_COSMOS_MISSION_PROFILE_CONTAINER",
            },
        )
        with patch.dict(
            os.environ,
            {
                "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME": "env-credential",
                "CANOPY_COSMOS_MISSION_PROFILE_CONTAINER": "env-profile",
            },
            clear=True,
        ):
            self.assertEqual(resolve_credential("cli-credential"), "cli-credential")
            self.assertEqual(resolve_credential(None), "env-credential")
            self.assertEqual(resolve_container("cli-profile"), "cli-profile")
            self.assertEqual(resolve_container(None), "env-profile")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                resolve_credential(None)
            with self.assertRaises(RuntimeError):
                resolve_container(None)
        self.assertNotIn('"mission-profiles"', self.source)

    def test_no_credential_values_are_logged(self):
        run = function_source(self.source, self.tree, "run")
        self.assertNotIn("print(credential", self.source)
        self.assertNotIn("print(service_credential", self.source)
        self.assertNotIn('"credential":', run)
        self.assertNotIn('"service_credential_name":', run)
        self.assertNotIn('"token":', run)

    def test_weekly_helper_is_canonical_side_effect_free_projection(self):
        helper = function_source(
            self.helper_source,
            self.helper_tree,
            "build_weekly_user_profile",
        )
        self.assertIn("profile_df", helper)
        self.assertIn("PROFILE_COLUMNS", helper)
        for forbidden in (
            ".collect(", ".toPandas(", ".write", "Cosmos", "dbutils",
            "groupBy(", 'F.lit("user_profile")', 'F.lit("v1")',
            'F.lit("active")', 'F.lit("delta_sync")',
        ):
            self.assertNotIn(forbidden, helper)

    def test_weekly_pipeline_reads_optional_profile_gold(self):
        source = function_source(
            self.pipeline_source,
            self.pipeline_tree,
            "weekly_user_profile",
        )
        self.assertIn("CANOPY_GOLD_MISSION_PROFILE_PATH", source)
        self.assertIn("_read_optional_delta(", source)
        self.assertIn("PROFILE_SCHEMA", source)
        self.assertIn("build_weekly_user_profile(profile_df)", source)
        self.assertNotIn("weekly_gold", source)
        self.assertNotIn("mission_response", source)

    def test_job_order_and_profile_runtime_wiring(self):
        self.assertEqual(
            [task["task_key"] for task in self.job["tasks"]],
            [
                "materialize_mission_response_weekly",
                "run_weekly_pipeline",
                "materialize_mission_profile",
                "publish_reward_ledger",
                "refresh_weekly_after_reward",
                "publish_weekly_cosmos",
            ],
        )
        profile = self.tasks["materialize_mission_profile"]
        self.assertEqual(
            profile["depends_on"],
            [{"task_key": "run_weekly_pipeline"}],
        )
        self.assertEqual(
            self.tasks["publish_reward_ledger"]["depends_on"],
            [{"task_key": "materialize_mission_profile"}],
        )
        parameters = profile["spark_python_task"]["parameters"]
        self.assertIn(
            "table:${var.catalog}.${var.schema}.weekly_gold",
            parameters,
        )
        self.assertIn("${var.mission_service_credential_name}", parameters)
        self.assertIn("${var.mission_profile_container_name}", parameters)
        self.assertEqual(
            self.bundle["variables"]["mission_profile_container_name"]["default"],
            "",
        )
        self.assertEqual(
            profile["environment_key"],
            "mission_response_materialization",
        )


if __name__ == "__main__":
    unittest.main()

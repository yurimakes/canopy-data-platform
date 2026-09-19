import ast
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT.parent
LEDGER = PIPELINES / "databricks" / "reward_ledger.py"
PUBLISHER = ROOT / "publish_reward_ledger.py"
BUNDLE = ROOT / "databricks.yml"


def function_source(source, tree, name):
    node = next(
        item for item in ast.walk(tree)
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node)


class RewardLedgerWiringStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger_source = LEDGER.read_text(encoding="utf-8")
        cls.publisher_source = PUBLISHER.read_text(encoding="utf-8")
        cls.ledger_tree = ast.parse(cls.ledger_source)
        cls.publisher_tree = ast.parse(cls.publisher_source)
        cls.bundle = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
        cls.job = cls.bundle["resources"]["jobs"]["weekly_analysis_job"]
        cls.tasks = {task["task_key"]: task for task in cls.job["tasks"]}

    def test_reward_calculation_source_supports_table_and_delta_path(self):
        source = function_source(
            self.ledger_source,
            self.ledger_tree,
            "_read_reward_calculation_source",
        )
        self.assertIn('source.startswith("table:")', source)
        self.assertIn("spark.table(table_name)", source)
        self.assertIn('spark.read.format("delta").load(source)', source)
        for column in (
            "user_id", "campaign_id", "week", "status", "payable",
            "points", "reason", "point_reason",
            "missions_completed_this_week", "policy_version",
        ):
            self.assertIn(f'"{column}"', self.ledger_source)

    def test_run_filters_one_explicit_scope_and_resyncs_history(self):
        source = function_source(self.ledger_source, self.ledger_tree, "run")
        self.assertIn('F.col("campaign_id") == campaign_id', source)
        self.assertIn('F.col("week") == week', source)
        self.assertIn("Resolved campaign_id required", source)
        self.assertIn("Resolved week required", source)
        self.assertIn("container = container or _get_container()", source)
        self.assertIn("sync_ledger_history_from_cosmos", source)
        self.assertIn("target=history_target", source)
        self.assertLess(
            source.index("process_reward_batch"),
            source.index("sync_ledger_history_from_cosmos"),
        )

    def test_non_payable_or_null_points_are_never_written(self):
        source = function_source(
            self.ledger_source,
            self.ledger_tree,
            "write_reward",
        )
        self.assertIn('not result_row.get("payable")', source)
        self.assertIn('result_row.get("points") is None', source)
        self.assertLess(source.index("not_payable"), source.index("create_item"))

    def test_reward_id_and_duplicate_handling_are_idempotent(self):
        id_source = function_source(
            self.ledger_source,
            self.ledger_tree,
            "make_reward_id",
        )
        write_source = function_source(
            self.ledger_source,
            self.ledger_tree,
            "write_reward",
        )
        self.assertIn('f"{user_id}_{campaign_id}_{week}"', id_source)
        self.assertIn("CosmosResourceExistsError", write_source)
        self.assertIn("container.read_item", write_source)
        self.assertIn('"status": "already_exists"', write_source)

    def test_cosmos_history_keeps_paid_and_adjusted_rows(self):
        source = function_source(
            self.ledger_source,
            self.ledger_tree,
            "read_ledger_partition",
        )
        self.assertIn("c.campaign_id = @campaign_id", source)
        self.assertIn("c.week_label = @week_label", source)
        self.assertIn('c.status = "paid"', source)
        self.assertIn('c.status = "adjusted"', source)

    def test_publisher_uses_existing_secret_and_container(self):
        source = function_source(
            self.publisher_source,
            self.publisher_tree,
            "_get_container",
        )
        self.assertIn("dbutils.secrets.get", source)
        self.assertIn("CosmosClient(endpoint, credential=credential)", source)
        self.assertIn("get_database_client", source)
        self.assertIn("get_container_client", source)
        self.assertNotIn("create_database", source)
        self.assertNotIn("create_container", source)
        self.assertNotIn("print(", self.publisher_source)
        self.assertNotIn("logging.", self.publisher_source)

    def test_publisher_requires_explicit_scope_and_calls_ledger(self):
        parse_source = function_source(
            self.publisher_source,
            self.publisher_tree,
            "parse_args",
        )
        for option in (
            "--campaign-id", "--week", "--reward-calc-source",
            "--endpoint", "--secret-scope", "--secret-key",
        ):
            self.assertIn(f'"{option}"', parse_source)
        main_source = function_source(
            self.publisher_source,
            self.publisher_tree,
            "main",
        )
        self.assertIn("reward_ledger.run(", main_source)
        self.assertIn("container=container", main_source)

    def test_job_parameters_are_explicit_and_not_hard_coded(self):
        parameters = {
            parameter["name"]: parameter["default"]
            for parameter in self.job["parameters"]
        }
        self.assertEqual(parameters, {"campaign_id": "", "week": ""})
        publish_parameters = self.tasks["publish_reward_ledger"][
            "spark_python_task"
        ]["parameters"]
        self.assertIn("{{job.parameters.campaign_id}}", publish_parameters)
        self.assertIn("{{job.parameters.week}}", publish_parameters)
        self.assertIn(
            "table:${var.catalog}.${var.schema}.reward_calculation",
            publish_parameters,
        )

    def test_job_task_order_and_incremental_refresh(self):
        task_order = [task["task_key"] for task in self.job["tasks"]]
        self.assertEqual(
            task_order,
            [
                "materialize_mission_response_weekly",
                "run_weekly_pipeline",
                "materialize_mission_profile",
                "publish_reward_ledger",
                "refresh_weekly_after_reward",
                "publish_weekly_cosmos",
            ],
        )
        self.assertEqual(
            self.tasks["publish_reward_ledger"]["depends_on"],
            [{"task_key": "materialize_mission_profile"}],
        )
        refresh = self.tasks["refresh_weekly_after_reward"]
        self.assertEqual(
            refresh["depends_on"],
            [{"task_key": "publish_reward_ledger"}],
        )
        self.assertEqual(
            refresh["pipeline_task"]["pipeline_id"],
            self.tasks["run_weekly_pipeline"]["pipeline_task"]["pipeline_id"],
        )
        self.assertNotIn("full_refresh", refresh["pipeline_task"])
        self.assertEqual(
            self.tasks["publish_weekly_cosmos"]["depends_on"],
            [{"task_key": "refresh_weekly_after_reward"}],
        )

    def test_reward_publisher_uses_verified_cosmos_dependency(self):
        environments = {
            environment["environment_key"]: environment["spec"]
            for environment in self.job["environments"]
        }
        self.assertEqual(
            environments["reward_publish"]["dependencies"],
            ["azure-cosmos==4.17.0"],
        )
        self.assertEqual(
            self.tasks["publish_reward_ledger"]["environment_key"],
            "reward_publish",
        )


if __name__ == "__main__":
    unittest.main()

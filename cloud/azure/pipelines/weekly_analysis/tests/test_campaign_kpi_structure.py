import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "weekly_pipeline.py"
HELPER = ROOT / "helpers" / "campaign_kpi.py"


class CampaignKpiStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_source = PIPELINE.read_text(encoding="utf-8")
        cls.helper_source = HELPER.read_text(encoding="utf-8")
        cls.pipeline_tree = ast.parse(cls.pipeline_source)
        cls.helper_tree = ast.parse(cls.helper_source)

    def test_campaign_helper_exists(self):
        names = {
            node.name
            for node in ast.walk(self.helper_tree)
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("build_campaign_kpi", names)

    def test_campaign_helper_has_no_driver_or_write_actions(self):
        for token in (
            ".collect(",
            ".toPandas(",
            ".save(",
            ".saveAsTable(",
            ".write.",
            "CosmosClient(",
        ):
            self.assertNotIn(token, self.helper_source)

    def test_pipeline_calls_campaign_helper(self):
        campaign = next(
            node
            for node in ast.walk(self.pipeline_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "campaign_kpi"
        )

        called = {
            node.func.id
            for node in ast.walk(campaign)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }

        self.assertIn("build_campaign_kpi_df", called)

    def test_campaign_is_not_placeholder(self):
        campaign = next(
            node
            for node in ast.walk(self.pipeline_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "campaign_kpi"
        )

        called = {
            node.func.id
            for node in ast.walk(campaign)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }

        self.assertNotIn("empty_result", called)

    def test_helper_imports_are_connected(self):
        source = self.pipeline_source

        self.assertIn(
            "from helpers.baseline_eligibility import build_baseline_eligibility",
            source,
        )
        self.assertIn(
            "from helpers.weekly_user_profile import build_weekly_user_profile",
            source,
        )
        self.assertIn(
            "build_campaign_kpi as build_campaign_kpi_df",
            source,
        )


if __name__ == "__main__":
    unittest.main()
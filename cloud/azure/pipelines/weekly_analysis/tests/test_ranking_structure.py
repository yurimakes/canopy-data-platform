import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "weekly_pipeline.py"
DATABRICKS = ROOT.parent / "databricks"
RANKING = DATABRICKS / "build_ranking.py"
POLICY = DATABRICKS / "ranking_policy.yaml"


class RankingStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_source = PIPELINE.read_text(encoding="utf-8")
        cls.ranking_source = RANKING.read_text(encoding="utf-8")
        cls.policy_source = POLICY.read_text(encoding="utf-8")
        cls.pipeline_tree = ast.parse(cls.pipeline_source)
        cls.ranking_tree = ast.parse(cls.ranking_source)

    def test_pipeline_ranking_is_connected(self):
        ranking = next(
            node
            for node in ast.walk(self.pipeline_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "ranking"
        )
        ranking_source = ast.get_source_segment(self.pipeline_source, ranking)

        self.assertIn("build_ranking_df", ranking_source)
        self.assertNotIn("empty_result", ranking_source)
        self.assertIn('"reward_ledger_history"', ranking_source)
        self.assertIn('"campaign_membership_raw"', ranking_source)

    def test_existing_ranking_transform_is_lakeflow_safe(self):
        build = next(
            node
            for node in ast.walk(self.ranking_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_ranking"
        )
        build_source = ast.get_source_segment(self.ranking_source, build)

        for token in (
            ".collect(",
            ".toPandas(",
            ".first(",
            ".save(",
            ".saveAsTable(",
            ".write.",
            "CosmosClient(",
        ):
            self.assertNotIn(token, build_source)

        self.assertNotIn(").count()", build_source)

    def test_ranking_uses_weekly_reward_contract(self):
        self.assertIn("scope: weekly", self.policy_source)
        self.assertIn("status_filter: [paid, adjusted]", self.policy_source)
        self.assertIn('F.col("week_label").alias("week")', self.ranking_source)
        self.assertIn('F.col("status").isin(status_filter)', self.ranking_source)

    def test_pipeline_maps_personal_and_department_rows(self):
        self.assertIn('F.lit("personal").alias("ranking_type")', self.pipeline_source)
        self.assertIn('F.lit("department").alias("ranking_type")', self.pipeline_source)
        self.assertIn('alias("reward_points")', self.pipeline_source)


if __name__ == "__main__":
    unittest.main()

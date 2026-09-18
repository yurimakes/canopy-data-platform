import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "databricks"
PUBLISHER = ROOT / "publish_ranking_to_cosmos.py"


class RankingPublisherStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PUBLISHER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _function_source(self, name):
        function = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return ast.get_source_segment(self.source, function)

    def test_reads_unified_weekly_ranking_table(self):
        self.assertIn('"CANOPY_RANKING_TABLE"', self.source)
        self.assertIn('"dbw_canopy_dev.weekly_analysis_scaffold.ranking"', self.source)
        self.assertNotIn("GOLD_PERSONAL_RANKING_PATH", self.source)
        self.assertNotIn("GOLD_DEPARTMENT_RANKING_PATH", self.source)

    def test_personal_publisher_filters_personal_rows(self):
        source = self._function_source("publish_personal")
        self.assertIn('F.col("ranking_type") == "personal"', source)
        self.assertIn('F.col("reward_points").alias("score")', source)

    def test_department_publisher_filters_department_rows(self):
        source = self._function_source("publish_department")
        self.assertIn('F.col("ranking_type") == "department"', source)
        self.assertIn('F.col("reward_points").alias("score")', source)

    def test_department_members_are_rebuilt_from_membership_snapshot(self):
        source = self._function_source("publish_department")
        self.assertIn("CAMPAIGN_MEMBERSHIP_PATH", source)
        self.assertIn('F.col("joined_at")', source)
        self.assertIn('F.col("left_at")', source)
        self.assertIn('F.collect_set("user_id")', source)

    def test_publisher_keeps_existing_cosmos_contract(self):
        self.assertIn('"ranking-snapshots"', self.source)
        self.assertIn('"snapshot_status": "finalized"', self.source)
        self.assertIn('"score_unit": "points"', self.source)
        self.assertIn('"member_user_ids"', self.source)


if __name__ == "__main__":
    unittest.main()

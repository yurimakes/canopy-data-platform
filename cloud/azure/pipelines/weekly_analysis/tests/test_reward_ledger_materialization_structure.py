import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "databricks"
TARGET = ROOT / "reward_ledger.py"


class RewardLedgerMaterializationStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TARGET.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _function_source(self, name):
        fn = next(
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return ast.get_source_segment(self.source, fn)

    def test_history_schema_keeps_paid_and_adjusted_rows(self):
        self.assertIn("adjusts_reward_id string", self.source)
        self.assertIn('LEDGER_HISTORY_STATUSES = ("paid", "adjusted")', self.source)

    def test_cosmos_sync_filters_campaign_week_and_status(self):
        source = self._function_source("read_ledger_partition")
        self.assertIn("c.campaign_id = @campaign_id", source)
        self.assertIn("c.week_label = @week_label", source)
        self.assertIn('c.status = "paid"', source)
        self.assertIn('c.status = "adjusted"', source)

    def test_partition_write_is_idempotent(self):
        source = self._function_source("write_ledger_partition")
        helper = self._function_source("_replace_history_partition")
        new_history = self._function_source("_write_new_history")
        self.assertIn("_replace_history_partition", source)
        self.assertIn('option("replaceWhere", predicate)', helper)
        self.assertIn('partitionBy("campaign_id", "week_label")', new_history)

    def test_sandbox_table_target_is_supported(self):
        resolver = self._function_source("_resolve_history_target")
        writer = self._function_source("_write_new_history")
        replacer = self._function_source("_replace_history_partition")
        self.assertIn('startswith("table:")', resolver)
        self.assertIn("saveAsTable", writer)
        self.assertIn("saveAsTable", replacer)

    def test_run_resyncs_history_from_cosmos(self):
        source = self._function_source("run")
        self.assertIn("sync_ledger_history_from_cosmos", source)
        self.assertNotIn("write_ledger_history(spark, outcomes)", source)

    def test_paid_upsert_preserves_existing_adjustments(self):
        source = self._function_source("write_ledger_history")
        self.assertIn(".merge(", source)
        self.assertIn("target.reward_id = source.reward_id", source)


if __name__ == "__main__":
    unittest.main()

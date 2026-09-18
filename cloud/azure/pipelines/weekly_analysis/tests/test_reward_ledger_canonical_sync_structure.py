"""Static safety checks for canonical Reward Ledger test materialization."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
TARGET = ROOT / "tools" / "azure" / "materialize_reward_ledger_canonical_test_partition.py"


class RewardLedgerCanonicalSyncStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TARGET.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_is_restricted_to_dedicated_test_campaign(self):
        self.assertIn('CAMPAIGN = "pipeline_test_weekly_20260918"', self.source)
        self.assertIn('CAMPAIGN.startswith("pipeline_test_weekly_")', self.source)

    def test_reuses_existing_team_cosmos_configuration(self):
        self.assertIn("sync_campaign_membership.job.json", self.source)
        self.assertIn('get_arg("--secret-scope")', self.source)
        self.assertIn('get_arg("--secret-key")', self.source)
        self.assertNotIn("canopy-scope", self.source)

    def test_writes_reward_ledger_canonical_path_only_through_existing_sync(self):
        self.assertIn("GOLD_REWARD_LEDGER_HISTORY_PATH", self.source)
        self.assertIn("sync_ledger_history_from_cosmos", self.source)
        self.assertNotIn("calculate_rewards(", self.source)

    def test_repeats_sync_for_idempotency(self):
        calls = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sync_ledger_history_from_cosmos"
        ]
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()

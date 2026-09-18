"""Static contract tests for Baseline Eligibility identity wiring.

These tests intentionally avoid importing PySpark. They verify that the Weekly
pipeline passes the synchronized campaign membership snapshot into the
eligibility helper and that the helper evaluates prior completed-week history
without replacing identity input with an empty placeholder.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "weekly_pipeline.py"
HELPER_PATH = ROOT / "helpers" / "baseline_eligibility.py"
SPARK_BASELINE_PATH = ROOT / "helpers" / "spark_baseline.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function not found: {name}")


class BaselineEligibilityIdentityStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_source = PIPELINE_PATH.read_text(encoding="utf-8")
        cls.helper_source = HELPER_PATH.read_text(encoding="utf-8")
        cls.spark_baseline_source = SPARK_BASELINE_PATH.read_text(encoding="utf-8")
        cls.pipeline_tree = parse(PIPELINE_PATH)
        cls.helper_tree = parse(HELPER_PATH)

    def test_pipeline_passes_membership_dataframe(self):
        function = find_function(self.pipeline_tree, "baseline_eligibility")
        source = ast.unparse(function)

        self.assertIn("campaign_membership_raw", source)
        self.assertIn("membership_df=membership_df", source)
        self.assertIn(
            "commute_scope_verified=COMMUTE_SCOPE_VERIFIED",
            source,
        )

    def test_pipeline_schema_preserves_observation_source(self):
        self.assertIn(
            "confirmed_trip_count BIGINT, observation_source STRING",
            self.pipeline_source,
        )

    def test_helper_does_not_replace_identity_with_empty_placeholder(self):
        self.assertNotIn(
            '"users": [],\n                "memberships": []',
            self.helper_source,
        )
        self.assertIn("membership_df: DataFrame | None = None", self.helper_source)
        self.assertIn("observation_context(", self.helper_source)

    def test_helper_uses_prior_completed_week_window(self):
        self.assertIn(
            ".rowsBetween(Window.unboundedPreceding, -1)",
            self.helper_source,
        )

    def test_helper_preserves_identity_errors_and_commute_gate(self):
        self.assertIn("identity_error", self.helper_source)
        self.assertIn("weekly_commute_scope_unverified", self.helper_source)

    def test_personal_baseline_preserves_observation_source(self):
        self.assertIn(
            'F.col("e.observation_source")',
            self.spark_baseline_source,
        )


if __name__ == "__main__":
    unittest.main()

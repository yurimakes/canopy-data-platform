"""Static contract tests for the Weekly Baseline pipeline.

These tests intentionally do not import PySpark.
They verify the module boundary and DAG wiring locally.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PIPELINE_PATH = ROOT / "weekly_pipeline.py"
HELPER_PATH = ROOT / "helpers" / "spark_baseline.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node

    raise AssertionError(f"Function not found: {name}")


def called_names(function: ast.FunctionDef) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)

    return names


def call_keywords(function: ast.FunctionDef, target_name: str) -> set[str]:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name) and node.func.id == target_name:
            return {
                keyword.arg
                for keyword in node.keywords
                if keyword.arg is not None
            }

    raise AssertionError(
        f"{function.name} does not call {target_name}"
    )


class BaselineHelperStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper_source = HELPER_PATH.read_text(encoding="utf-8")
        cls.helper_tree = parse(HELPER_PATH)
        cls.pipeline_tree = parse(PIPELINE_PATH)

    def test_expected_helper_functions_exist(self):
        expected = {
            "build_personal_baseline",
            "select_personal_ready_users",
            "build_global_eligibility",
            "build_global_baseline",
            "build_baseline_gold",
        }

        actual = {
            node.name
            for node in self.helper_tree.body
            if isinstance(node, ast.FunctionDef)
        }

        self.assertTrue(expected.issubset(actual))

    def test_helper_has_no_lakeflow_declarations(self):
        self.assertNotIn("@dp.", self.helper_source)
        self.assertNotIn("pyspark import pipelines", self.helper_source)

    def test_helper_does_not_write_or_call_cosmos(self):
        forbidden = (
            ".write",
            "CosmosClient",
            "spark.write",
            "dbutils.jobs",
        )

        for token in forbidden:
            self.assertNotIn(token, self.helper_source)

    def test_personal_pipeline_calls_helper(self):
        function = find_function(
            self.pipeline_tree,
            "personal_baseline",
        )

        self.assertIn(
            "build_personal_baseline_df",
            called_names(function),
        )

        self.assertEqual(
            call_keywords(
                function,
                "build_personal_baseline_df",
            ),
            {
                "weekly",
                "eligibility",
                "baseline_policy_version",
                "commute_scope_verified",
                "eligibility_policy",
            },
        )

    def test_personal_ready_pipeline_calls_helper(self):
        function = find_function(
            self.pipeline_tree,
            "personal_ready_users",
        )

        self.assertIn(
            "select_personal_ready_users",
            called_names(function),
        )

        self.assertEqual(
            call_keywords(
                function,
                "select_personal_ready_users",
            ),
            {"eligibility_policy"},
        )

    def test_global_eligibility_pipeline_calls_helper(self):
        function = find_function(
            self.pipeline_tree,
            "global_eligibility",
        )

        self.assertIn(
            "build_global_eligibility",
            called_names(function),
        )

        self.assertEqual(
            call_keywords(
                function,
                "build_global_eligibility",
            ),
            {
                "personal",
                "ready",
                "eligibility_policy",
            },
        )

    def test_global_baseline_pipeline_calls_helper(self):
        function = find_function(
            self.pipeline_tree,
            "global_baseline",
        )

        self.assertIn(
            "build_global_baseline_df",
            called_names(function),
        )

        self.assertEqual(
            call_keywords(
                function,
                "build_global_baseline_df",
            ),
            {
                "ready",
                "eligibility",
                "baseline_policy_version",
                "eligibility_policy",
            },
        )


    def test_baseline_gold_pipeline_calls_helper(self):
        function = find_function(
            self.pipeline_tree,
            "baseline_gold",
        )

        self.assertIn(
            "build_baseline_gold_df",
            called_names(function),
        )
        self.assertNotIn(
            "empty_result",
            called_names(function),
        )

        self.assertEqual(
            call_keywords(
                function,
                "build_baseline_gold_df",
            ),
            {
                "personal",
                "global_baseline",
                "personal_fields",
                "global_fields",
            },
        )


if __name__ == "__main__":
    unittest.main()
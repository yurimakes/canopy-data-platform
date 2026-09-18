"""Static wiring tests for Behavior Change in the Weekly pipeline.

These tests do not import PySpark. They verify that the existing observational
Behavior Change calculation is exposed as a DataFrame transform and that the
Weekly pipeline calls it instead of returning a placeholder.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "weekly_pipeline.py"
HELPER_PATH = ROOT.parent / "databricks" / "build_behavior_change.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
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


class BehaviorChangeStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_source = PIPELINE_PATH.read_text(encoding="utf-8")
        cls.helper_source = HELPER_PATH.read_text(encoding="utf-8")
        cls.pipeline_tree = parse(PIPELINE_PATH)
        cls.helper_tree = parse(HELPER_PATH)

    def test_dataframe_builder_exists(self):
        names = {
            node.name
            for node in ast.walk(self.helper_tree)
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("build_behavior_change", names)

    def test_helper_has_no_write_or_cosmos_actions(self):
        for token in (
            ".write.",
            ".save(",
            ".saveAsTable(",
            "CosmosClient(",
            "dbutils.jobs",
        ):
            self.assertNotIn(token, self.helper_source)

    def test_pipeline_imports_behavior_builder(self):
        self.assertIn(
            "from build_behavior_change import build_behavior_change as build_behavior_change_df",
            self.pipeline_source,
        )

    def test_pipeline_calls_behavior_builder(self):
        function = find_function(self.pipeline_tree, "behavior_change")
        self.assertIn("build_behavior_change_df", called_names(function))

    def test_behavior_change_is_not_placeholder(self):
        function = find_function(self.pipeline_tree, "behavior_change")
        self.assertNotIn("empty_result", called_names(function))

    def test_behavior_change_reads_weekly_gold(self):
        function = find_function(self.pipeline_tree, "behavior_change")
        string_constants = {
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("weekly_gold", string_constants)


if __name__ == "__main__":
    unittest.main()

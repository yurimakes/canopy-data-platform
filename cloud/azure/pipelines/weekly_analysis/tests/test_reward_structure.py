"""Local Reward wiring and expression tests without a PySpark runtime."""

from __future__ import annotations

import ast
import math
import unittest
from numbers import Real
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "weekly_pipeline.py"
HELPER = ROOT / "helpers" / "reward.py"
POLICY = ROOT.parent / "databricks" / "reward_policy.yaml"
MISSION_SCHEMA = ROOT.parents[3] / "shared" / "schemas" / "mission" / "mission_response_weekly.schema.json"

# Test-only value. It is not a Reward policy decision.
TEST_POLICY = {
    "policy_version": "reward-test-only",
    "points": {"no_change": 0},
    "point_formula": {"conversion_rate": 25.0},
}


def function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def isolated_function(tree: ast.Module, name: str, namespace: dict):
    module = ast.Module(body=[function(tree, name)], type_ignores=[])
    exec(compile(module, str(HELPER), "exec"), namespace)
    return namespace[name]


class Expr:
    def __init__(self, evaluate):
        self.evaluate = evaluate

    @staticmethod
    def field(name):
        return Expr(lambda row: row[name])

    def isNull(self):
        return Expr(lambda row: self.evaluate(row) is None)

    def isNotNull(self):
        return Expr(lambda row: self.evaluate(row) is not None)

    def __and__(self, other):
        return Expr(lambda row: bool(self.evaluate(row)) and bool(other.evaluate(row)))

    def __or__(self, other):
        return Expr(lambda row: bool(self.evaluate(row)) or bool(other.evaluate(row)))

    def __invert__(self):
        return Expr(lambda row: not self.evaluate(row))

    def __sub__(self, other):
        return Expr(lambda row: self.evaluate(row) - other.evaluate(row))

    def __truediv__(self, other):
        return Expr(lambda row: self.evaluate(row) / other.evaluate(row))

    def __eq__(self, other):
        return Expr(lambda row: self.evaluate(row) == other)

    def __gt__(self, other):
        return Expr(lambda row: self.evaluate(row) > other)

    def __le__(self, other):
        return Expr(lambda row: self.evaluate(row) <= other.evaluate(row))

    def cast(self, data_type):
        if data_type != "double":
            raise AssertionError(data_type)
        return Expr(
            lambda row: None if self.evaluate(row) is None
            else float(self.evaluate(row))
        )


class Case:
    def __init__(self, condition, value):
        self.branches = [(condition, value)]

    def when(self, condition, value):
        self.branches.append((condition, value))
        return self

    def otherwise(self, default):
        def evaluate(row):
            for condition, value in self.branches:
                if condition.evaluate(row):
                    return value.evaluate(row)
            return default.evaluate(row)

        return Expr(evaluate)


class FakeFunctions:
    @staticmethod
    def lit(value):
        return Expr(lambda row: value)

    @staticmethod
    def when(condition, value):
        return Case(condition, value)

    @staticmethod
    def greatest(left, right):
        return Expr(lambda row: max(left.evaluate(row), right.evaluate(row)))


class RewardStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_source = PIPELINE.read_text(encoding="utf-8")
        cls.helper_source = HELPER.read_text(encoding="utf-8")
        cls.pipeline_tree = ast.parse(cls.pipeline_source)
        cls.helper_tree = ast.parse(cls.helper_source)

    def test_materialized_view_calls_helper_with_internal_inputs(self):
        reward = function(self.pipeline_tree, "reward_calculation")
        source = ast.get_source_segment(self.pipeline_source, reward)
        self.assertIn("build_reward_calculation_df", source)
        self.assertNotIn("empty_result", source)
        self.assertIn('spark.read.table("weekly_gold")', source)
        self.assertIn('spark.read.table("personal_baseline")', source)
        self.assertIn('spark.read.table("global_baseline")', source)
        self.assertIn('"mission_response_weekly"', source)
        self.assertIn("_read_optional_delta", source)
        self.assertIn("schema=REWARD_CALC_SCHEMA", self.pipeline_source)
        self.assertIn('"reward_policy.yaml"', self.pipeline_source)
        self.assertIn('"PATH_NOT_FOUND"', self.pipeline_source)

    def test_output_contract_and_no_side_effects(self):
        self.assertEqual(
            (
                "user_id", "campaign_id", "week", "status", "payable", "points",
                "reason", "point_reason", "missions_completed_this_week", "policy_version",
            ),
            tuple(
                ast.literal_eval(node.value)
                for node in self.helper_tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "REWARD_COLUMNS"
                        for target in node.targets)
            )[0],
        )
        for forbidden in (
            ".collect(", ".toPandas(", ".write", ".save(",
            "Cosmos", "dbutils", "spark.read", ".count()", ".first(",
        ):
            self.assertNotIn(forbidden, self.helper_source)

    def test_canonical_mission_dates_join_to_iso_week(self):
        import json

        canonical = json.loads(MISSION_SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(
            {"campaign_id", "user_id", "week_start", "week_end", "completed"}
            <= set(canonical["required"])
        )
        self.assertNotIn("week", canonical["required"])
        spine = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "_week_spine")
        )
        self.assertIn('F.expr("date_add(_week_start, 7)")', spine)
        self.assertIn('"_week_end_exclusive"', spine)
        self.assertNotIn('date_add(_week_start, 6)', spine)
        source = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "_mission_completions")
        )
        self.assertIn('F.to_date(F.col("m.week_start")) == F.col("w._week_start")', source)
        self.assertIn(
            'F.to_date(F.col("m.week_end")) == F.col("w._week_end_exclusive")',
            source,
        )
        self.assertIn('F.col("m.campaign_id") == F.col("w.campaign_id")', source)
        self.assertIn('F.col("m.user_id").alias("user_id")', source)
        self.assertNotIn('F.col("m.week")', source)

    def test_unset_rate_fails_closed(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        self.assertEqual(validate(TEST_POLICY), 25.0)
        canonical = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        self.assertIsNone(canonical["point_formula"]["conversion_rate"])
        for invalid in (canonical, {"point_formula": {}},
                        {"point_formula": {"conversion_rate": 0}}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "point_formula.conversion_rate"
            ):
                validate(invalid)

    def test_status_precedence_with_test_only_policy(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        self.assertEqual(validate(TEST_POLICY), 25.0)
        classify = isolated_function(
            self.helper_tree, "_classify_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        expression = classify(
            Expr.field("personal"), Expr.field("global"),
            Expr.field("actual"), Expr.field("has_current"),
        )
        cases = (
            ({"personal": None, "global": None, "actual": 80.0,
              "has_current": True}, "not_eligible"),
            ({"personal": 100.0, "global": 120.0, "actual": 80.0,
              "has_current": True}, "improved"),
            ({"personal": 80.0, "global": 100.0, "actual": 90.0,
              "has_current": True}, "maintained"),
            ({"personal": 80.0, "global": 100.0, "actual": 110.0,
              "has_current": True}, "no_change"),
            ({"personal": 100.0, "global": 120.0, "actual": None,
              "has_current": False}, "not_eligible"),
        )
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(expression.evaluate(row), expected)

    def test_points_for_each_status_with_test_only_policy(self):
        rate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )(TEST_POLICY)
        score = isolated_function(
            self.helper_tree, "_points_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        expression = score(
            Expr.field("status"), Expr.field("delta"), TEST_POLICY, rate,
        )
        for row, expected in (
            ({"status": "improved", "delta": 20.0}, 0.8),
            ({"status": "maintained", "delta": 10.0}, 0.4),
            ({"status": "no_change", "delta": None}, 0.0),
            ({"status": "not_eligible", "delta": None}, None),
        ):
            with self.subTest(row=row):
                self.assertEqual(expression.evaluate(row), expected)

    def test_current_performance_and_points_formula_structure(self):
        source = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "build_reward_calculation")
        )
        self.assertIn('F.col("total_distance_m") > 0', source)
        self.assertIn('(F.col("total_kg_co2e") * 1000.0)', source)
        self.assertIn('(F.col("total_distance_m") / 1000.0)', source)
        self.assertIn('F.col("_trip_count") > 0', source)
        self.assertIn('_points_for_status(F.col("status"), F.col("_delta"), policy, rate)', source)
        self.assertIn('F.col("_personal") - F.col("_actual")', source)
        self.assertIn('F.col("_global") - F.col("_actual")', source)
        self.assertIn('F.col("status") != "not_eligible"', source)
        point_source = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "_points_for_status")
        )
        self.assertIn('F.greatest(delta, F.lit(0.0)) / F.lit(rate)', point_source)


if __name__ == "__main__":
    unittest.main()

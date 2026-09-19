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
BUNDLE = ROOT / "databricks.yml"
POLICY = ROOT.parent / "databricks" / "reward_policy.yaml"
ORIGINAL_REWARD = ROOT.parent / "databricks" / "calculate_reward.py"
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

    def __ne__(self, other):
        return Expr(lambda row: self.evaluate(row) != other)

    def __gt__(self, other):
        return Expr(lambda row: self.evaluate(row) > other)

    def __le__(self, other):
        return Expr(lambda row: self.evaluate(row) <= other.evaluate(row))

    def cast(self, data_type):
        if data_type not in {"double", "string"}:
            raise AssertionError(data_type)
        convert = float if data_type == "double" else str
        return Expr(
            lambda row: None if self.evaluate(row) is None
            else convert(self.evaluate(row))
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

    @staticmethod
    def concat(*parts):
        return Expr(lambda row: "".join(part.evaluate(row) for part in parts))


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
        self.assertIn(
            'conversion_rate_override=REWARD_CONVERSION_RATE_OVERRIDE',
            source,
        )
        self.assertIn(
            '"canopy.reward.conversion_rate_override"',
            self.pipeline_source,
        )
        bundle_source = BUNDLE.read_text(encoding="utf-8")
        self.assertIn(
            'canopy.reward.conversion_rate_override: "1.0"',
            bundle_source,
        )
        self.assertIn("DEV_ONLY", bundle_source)

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

    def test_unset_rate_can_build_result_but_invalid_rate_fails(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        self.assertEqual(validate(TEST_POLICY), (25.0, False))
        canonical = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        self.assertIsNone(canonical["point_formula"]["conversion_rate"])
        self.assertEqual(validate(canonical), (None, False))
        self.assertEqual(validate({"point_formula": {}}), (None, False))
        for invalid in (0, -1, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "point_formula.conversion_rate"
            ):
                validate({"point_formula": {"conversion_rate": invalid}})

    def test_canonical_rate_precedes_dev_override(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        self.assertEqual(validate(TEST_POLICY, "1.0"), (25.0, False))

    def test_null_canonical_uses_valid_override_and_rejects_invalid_override(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        canonical = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(validate(canonical, "1.0"), (1.0, True))
        for invalid in ("0", "-1", "nan", "inf", "not-a-number"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "canopy.reward.conversion_rate_override"
            ):
                validate(canonical, invalid)

    def test_status_precedence_with_test_only_policy(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        self.assertEqual(validate(TEST_POLICY), (25.0, False))
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

    def test_points_reasons_and_payable_with_configured_test_rate(self):
        validate = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )
        rate, uses_dev_override = validate(TEST_POLICY)
        score = isolated_function(
            self.helper_tree, "_points_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        reason = isolated_function(
            self.helper_tree, "_point_reason_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        payable = isolated_function(
            self.helper_tree, "_payable_for_status", {"Column": Expr}
        )
        points_expression = score(
            Expr.field("status"), Expr.field("delta"), TEST_POLICY, rate,
        )
        reason_expression = reason(
            Expr.field("status"), Expr.field("delta"), rate, uses_dev_override,
        )
        payable_expression = payable(Expr.field("status"), points_expression)
        for row, expected_points, expected_payable in (
            ({"status": "improved", "delta": 20.0}, 0.8, True),
            ({"status": "maintained", "delta": 10.0}, 0.4, True),
            ({"status": "no_change", "delta": None}, 0.0, True),
            ({"status": "not_eligible", "delta": None}, None, False),
        ):
            with self.subTest(row=row):
                self.assertEqual(points_expression.evaluate(row), expected_points)
                self.assertEqual(payable_expression.evaluate(row), expected_payable)
                self.assertIsInstance(reason_expression.evaluate(row), str)

    def test_canonical_null_rate_holds_improved_and_maintained(self):
        canonical = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        rate, uses_dev_override = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )(canonical)
        score = isolated_function(
            self.helper_tree, "_points_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        reason = isolated_function(
            self.helper_tree, "_point_reason_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        payable = isolated_function(
            self.helper_tree, "_payable_for_status", {"Column": Expr}
        )
        points_expression = score(
            Expr.field("status"), Expr.field("delta"), canonical, rate,
        )
        reason_expression = reason(
            Expr.field("status"), Expr.field("delta"), rate, uses_dev_override,
        )
        payable_expression = payable(Expr.field("status"), points_expression)
        for row, expected_points, expected_payable, expected_reason in (
            ({"status": "improved", "delta": 20.0}, None, False,
             "point_formula.conversion_rate not configured in policy"),
            ({"status": "maintained", "delta": 10.0}, None, False,
             "point_formula.conversion_rate not configured in policy"),
            ({"status": "no_change", "delta": None}, 0.0, True,
             "policy.points.no_change"),
            ({"status": "not_eligible", "delta": None}, None, False,
             "not_eligible"),
        ):
            with self.subTest(row=row):
                self.assertEqual(points_expression.evaluate(row), expected_points)
                self.assertEqual(payable_expression.evaluate(row), expected_payable)
                self.assertEqual(reason_expression.evaluate(row), expected_reason)

    def test_dev_override_maps_delta_to_points_and_marks_reason(self):
        canonical = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        rate, uses_dev_override = isolated_function(
            self.helper_tree, "_conversion_rate", {"math": math, "Real": Real}
        )(canonical, "1.0")
        score = isolated_function(
            self.helper_tree, "_points_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        reason = isolated_function(
            self.helper_tree, "_point_reason_for_status",
            {"F": FakeFunctions, "Column": Expr},
        )
        row = {"status": "improved", "delta": 20.0}
        points = score(
            Expr.field("status"), Expr.field("delta"), canonical, rate,
        ).evaluate(row)
        point_reason = reason(
            Expr.field("status"),
            Expr.field("delta"),
            rate,
            uses_dev_override,
        ).evaluate(row)
        self.assertEqual(points, 20.0)
        self.assertEqual(
            point_reason,
            "max(delta=20.0, 0) / conversion_rate(1.0) [dev_override]",
        )

    def test_original_calculator_does_not_mark_null_points_payable(self):
        original = ORIGINAL_REWARD.read_text(encoding="utf-8")
        self.assertIn(
            '"payable": status != "not_eligible" and points is not None',
            original,
        )

    def test_current_performance_and_points_formula_structure(self):
        source = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "build_reward_calculation")
        )
        self.assertIn('F.col("total_distance_m") > 0', source)
        self.assertIn('(F.col("total_kg_co2e") * 1000.0)', source)
        self.assertIn('(F.col("total_distance_m") / 1000.0)', source)
        self.assertIn('F.col("_trip_count") > 0', source)
        self.assertIn('_points_for_status(F.col("status"), F.col("_delta"), policy, rate)', source)
        self.assertIn("_point_reason_for_status(", source)
        self.assertIn("uses_dev_override", source)
        self.assertIn('F.col("_personal") - F.col("_actual")', source)
        self.assertIn('F.col("_global") - F.col("_actual")', source)
        self.assertIn('_payable_for_status(F.col("status"), F.col("points"))', source)
        point_source = ast.get_source_segment(
            self.helper_source, function(self.helper_tree, "_points_for_status")
        )
        self.assertIn('F.greatest(delta, F.lit(0.0)) / F.lit(rate)', point_source)


if __name__ == "__main__":
    unittest.main()

"""주간 연결 계약 검사. Azure 실행 및 데이터 쓰기 없음."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import unittest

import jsonschema
from pyspark.sql import types as T

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "cloud/azure/pipelines/weekly_analysis"
spec = importlib.util.spec_from_file_location("weekly_contract_test", MODULE / "weekly_pipeline.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def fixture():
    manifest = runtime.load_contracts()
    manifest["run"].update(campaign_id="pipeline_test_contract", closed_week_start="2026-09-14",
                           evaluation_week_start="2026-09-21")
    return manifest


def spark_type(schema):
    choices = set(runtime.field_types(schema)) - {"null"}
    if "object" in choices:
        if not schema.get("properties") and isinstance(schema.get("additionalProperties"), dict):
            return T.MapType(T.StringType(), spark_type(schema["additionalProperties"]))
        return T.StructType([T.StructField(name, spark_type(child), True)
                             for name, child in schema.get("properties", {}).items()])
    if "array" in choices:
        return T.ArrayType(spark_type(schema["items"]))
    return {"string": T.StringType(), "integer": T.LongType(), "number": T.DoubleType(),
            "boolean": T.BooleanType()}[next(iter(choices))]


class WeeklyContractTests(unittest.TestCase):
    def test_existing_contracts_are_valid_and_preserve_weekly_schema(self):
        m = fixture()
        for contract in m["contracts"].values():
            if contract["json_schema"]:
                jsonschema.Draft202012Validator.check_schema(contract["json_schema"])
        self.assertEqual(m["contracts"]["weekly"]["json_schema"], json.loads(
            (ROOT / "shared/schemas/baseline/weekly_user_gold.schema.json").read_text(encoding="utf-8")))

    def test_weekly_only_does_not_require_other_teams(self):
        context, stages, sources = runtime.preflight(fixture())
        self.assertEqual([s["output"] for s in stages], ["weekly_gold"])
        self.assertEqual(sources, ["final_trips"])
        self.assertEqual(context["closed_week"], "2026-W38")

    def test_korean_week_boundary_and_next_week(self):
        ctx = runtime.run_context(fixture()["run"])
        self.assertEqual(ctx["start_utc"], "2026-09-13T15:00:00+00:00")
        self.assertEqual(ctx["end_utc"], "2026-09-20T15:00:00+00:00")
        self.assertEqual(ctx["evaluation_week"], "2026-W39")
        bad = fixture()["run"]
        bad["evaluation_week_start"] = "2026-09-28"
        with self.assertRaises(ValueError):
            runtime.run_context(bad)

    def test_year_boundary(self):
        c = fixture()["run"]
        c.update(closed_week_start="2026-12-28", evaluation_week_start="2027-01-04")
        c = runtime.run_context(c)
        self.assertEqual(c["closed_week"], "2026-W53")
        self.assertEqual(c["evaluation_week"], "2027-W01")

    def test_profile_does_not_depend_on_behavior_or_baseline(self):
        m = fixture()
        m["run"]["enabled_outputs"] = ["mission_profile_gold"]
        stages, sources = runtime.execution_plan(m)
        self.assertEqual([s["output"] for s in stages], ["weekly_gold", "mission_profile_gold"])
        self.assertEqual(sources, ["final_trips", "mission_responses"])

    def test_ranking_uses_paid_history_not_weekly_carbon(self):
        m = fixture()
        m["run"]["enabled_outputs"] = ["ranking_gold"]
        stages, sources = runtime.execution_plan(m)
        self.assertEqual([s["output"] for s in stages], ["ranking_gold"])
        self.assertEqual(sources, ["department_memberships", "reward_postings"])
        with self.assertRaisesRegex(ValueError, "계약 미제출"):
            runtime.preflight(m)

    def test_cycle_is_rejected(self):
        m = fixture()
        m["stages"][0]["inputs"]["cycle"] = "weekly_gold"
        with self.assertRaisesRegex(ValueError, "순환"):
            runtime.execution_plan(m)

    def test_unknown_outputs_and_disabled_code_fail(self):
        m = fixture()
        m["run"]["enabled_outputs"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "출력 등록 누락"):
            runtime.execution_plan(m)
        m = fixture()
        m["stages"][0]["implemented"] = False
        with self.assertRaisesRegex(ValueError, "계산 코드 연결"):
            runtime.preflight(m)

    def test_production_rejects_test_path_and_unpinned_inputs(self):
        m = fixture()
        m["run"].update(test_mode=False, commute_scope_verified=True)
        with self.assertRaisesRegex(ValueError, "테스트 입력"):
            runtime.preflight(m)
        m["sources"]["final_trips"]["location"] = "abfss://gold@example.dfs.core.windows.net/final"
        with self.assertRaisesRegex(ValueError, "version"):
            runtime.preflight(m)

    def test_schema_types_missing_fields_and_nested_rules(self):
        m = fixture()
        for contract in m["contracts"].values():
            schema = contract["json_schema"]
            if schema:
                self.assertTrue(runtime.schema_rule(spark_type(schema), schema))
        schema = m["contracts"]["weekly"]["json_schema"]
        wrong = spark_type(schema)
        wrong.fields = [f for f in wrong.fields if f.name != "total_distance_m"]
        with self.assertRaisesRegex(ValueError, "total_distance_m"):
            runtime.schema_rule(wrong, schema)
        wrong = spark_type(schema)
        for field in wrong.fields:
            if field.name == "trip_count":
                field.dataType = T.StringType()
        with self.assertRaises(TypeError):
            runtime.schema_rule(wrong, schema)
        trip = m["contracts"]["final_trip"]["json_schema"]
        rule = runtime.schema_rule(spark_type(trip), trip)
        self.assertIn("forall(`segments`", rule)
        self.assertIn("kgCO2e", rule)

    def test_null_ratio_and_finite_number_contract(self):
        null_ratio = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
        expr = runtime.schema_rule(T.DoubleType(), null_ratio, "ratio")
        self.assertIn("ratio IS NULL OR", expr)
        self.assertIn("isnan", expr)

    def test_hooks_match_registry_and_have_no_driver_actions(self):
        m = fixture()
        tree = ast.parse((MODULE / "weekly_pipeline.py").read_text(encoding="utf-8"))
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for stage in m["stages"]:
            f = functions[stage["function"]]
            self.assertEqual([a.arg for a in f.args.args], ["inputs", "context"])
            if not stage["implemented"]:
                self.assertIsInstance(f.body[0], ast.Raise)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if ast.unparse(node.func.value) != "F":
                    self.assertNotIn(node.func.attr, {"collect", "count", "save", "saveAsTable", "upsert_item"})


if __name__ == "__main__":
    unittest.main()

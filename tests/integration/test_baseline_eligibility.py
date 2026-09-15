import copy
from pathlib import Path
import sys
import unittest
import os
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "cloud/azure/pipelines/databricks"
sys.path.insert(0, str(RUNTIME))
from baseline_eligibility import (load_eligibility_policy, evaluate_personal_eligibility,
                                  evaluate_global_eligibility, observation_context)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_eligibility_policy()

    def test_personal_A_to_E(self):
        for case, days, trips, distance, carbon, expected in [
            ("A", 6, 6, 1000, 1, "collecting"),
            ("B", 7, 5, 1000, 1, "collecting"),
            ("C", 7, 6, 1000, 1, "ready"),
            ("D", 7, 6, 0, 1, "collecting"),
            ("E", 7, 6, 1000, None, "collecting"),
        ]:
            with self.subTest(case=case):
                result = evaluate_personal_eligibility(days, trips, distance, carbon, self.policy)
                self.assertEqual(result["status"], expected)

    def test_global_F_G_H_counts_are_eligible_not_registered(self):
        for case, count, status in [("F", 5, "collecting"), ("G", 6, "ready"), ("H", 4, "collecting")]:
            with self.subTest(case=case):
                self.assertEqual(evaluate_global_eligibility(count, self.policy)["status"], status)

    def test_thresholds_come_from_yaml_not_gate_constants(self):
        p = copy.deepcopy(self.policy)
        p["personal"]["minimum_observation_days"] = 9
        p["personal"]["minimum_confirmed_commute_trips"] = 8
        p["global"]["minimum_eligible_participants"] = 3
        self.assertEqual(evaluate_personal_eligibility(7, 6, 1, 0, p)["status"], "collecting")
        self.assertEqual(evaluate_personal_eligibility(9, 8, 1, 0, p)["status"], "ready")
        self.assertEqual(evaluate_global_eligibility(3, p)["status"], "ready")

    def test_invalid_numbers_and_zero_emissions(self):
        for carbon in (None, float("nan"), float("inf"), -1, True, "1"):
            self.assertEqual(evaluate_personal_eligibility(7, 6, 1, carbon, self.policy)["status"], "collecting")
        self.assertEqual(evaluate_personal_eligibility(7, 6, 1, 0, self.policy)["status"], "ready")

    def test_membership_priority_elapsed_days_and_legacy_user_fallback(self):
        data = {"users": [{"user_id": "u", "created_at": "2026-01-01T00:00:00Z"}],
                "memberships": [{"user_id": "u", "campaign_id": "c", "joined_at": "2026-09-01T09:00:00+09:00"}]}
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", data)[:2], (7, "membership.joined_at"))
        self.assertEqual(observation_context("u", "c", "2026-09-07T23:59:59Z", data)[0], 6)
        self.assertEqual(observation_context("u", "other", "2026-09-08T00:00:00Z", data)[1], "user.created_at")
        self.assertEqual(observation_context("missing", "c", "2026-09-08T00:00:00Z", data)[2], "joined_at_missing")
        data["memberships"][0]["joined_at"] = "invalid"
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", data)[2], "invalid_joined_at")


class PersonalGateTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        self.pdf = pd.DataFrame([
            {"user_id": "u", "campaign_id": "c", "week": "2026-W36", "trip_count": 6,
             "total_distance_m": 10000.0, "total_kg_co2e": 1.2},
            {"user_id": "u", "campaign_id": "c", "week": "2026-W37", "trip_count": 2,
             "total_distance_m": 2000.0, "total_kg_co2e": 0.2},
        ])
        self.identities = {"users": [{"user_id": "u", "created_at": "2026-08-31T00:00:00Z"}]}

    def compute(self, **kwargs):
        from build_personal_baseline import _compute_personal_baseline
        return _compute_personal_baseline(self.pdf, "baseline-policy-v3",
                                         identities=kwargs.pop("identities", self.identities),
                                         commute_scope_verified=kwargs.pop("commute_scope_verified", True), **kwargs)

    def test_gate_before_existing_formula_and_weekly_input_unchanged(self):
        original = self.pdf.copy(deep=True)
        result = self.compute()
        self.assertEqual(result.iloc[0]["status"], "collecting")
        self.assertTrue(__import__("pandas").isna(result.iloc[0]["value"]))
        self.assertEqual(result.iloc[0]["primary_baseline"], "population")
        ready = result.iloc[1]
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["value"], 120.0)  # Original 1200 g / 10 km.
        self.assertEqual(ready["baseline_g_co2e_per_km"], ready["value"])
        self.assertEqual(ready["policy_version"], "baseline-policy-v3")
        self.assertEqual(ready["eligibility_policy_version"], "eligibility-v1")
        __import__("pandas").testing.assert_frame_equal(original, self.pdf)

    def test_missing_identity_or_unverified_commute_never_computes(self):
        for args in ({"identities": {}}, {"commute_scope_verified": False}):
            result = self.compute(**args)
            self.assertTrue((result.status == "collecting").all())
            self.assertTrue(result.value.isna().all())

    def test_personal_A_B_D_E_skip_ratio(self):
        for case in ("days", "trips", "distance", "carbon"):
            self.setUp()
            if case == "days":
                self.identities["users"][0]["created_at"] = "2026-09-01T00:00:00Z"
            else:
                column, value = {"trips": ("trip_count", 5), "distance": ("total_distance_m", 0),
                                 "carbon": ("total_kg_co2e", float("nan"))}[case]
                self.pdf.loc[0, column] = value
            result = self.compute().iloc[1]
            self.assertEqual(result["status"], "collecting", case)
            self.assertTrue(__import__("pandas").isna(result["value"]), case)

    def test_duplicate_weeks_rejected(self):
        self.pdf = __import__("pandas").concat([self.pdf, self.pdf])
        with self.assertRaisesRegex(ValueError, "Duplicate Weekly"):
            self.compute()

    def test_invalid_strings_and_zero_carbon_in_actual_personal_gate(self):
        for value in ("invalid", None, float("inf"), -1):
            self.setUp()
            self.pdf["total_kg_co2e"] = self.pdf["total_kg_co2e"].astype(object)
            self.pdf.loc[0, "total_kg_co2e"] = value
            self.assertEqual(self.compute().iloc[1]["status"], "collecting")
        self.setUp()
        self.pdf["total_kg_co2e"] = 0.0
        row = self.compute().iloc[1]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["value"], 0.0)


@unittest.skipUnless(os.environ.get("CANOPY_TEST_SPARK") == "1", "Set CANOPY_TEST_SPARK=1 with Java 17/21 for real Spark integration")
class SparkGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyspark.sql import SparkSession
        cls.spark = (SparkSession.builder.master("local[1]").appName("canopy-eligibility-tests")
                     .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "1")
                     .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def personal(self, ready_count, total=None):
        from pyspark.sql import functions as F
        return self.spark.range(total or ready_count).select(
            F.col("id").cast("string").alias("user_id"), F.lit("c").alias("campaign_id"),
            F.lit("2026-W37").alias("week"),
            F.when(F.col("id") < ready_count, "ready").otherwise("collecting").alias("status"),
            (F.col("id") + 100).cast("double").alias("baseline_g_co2e_per_km"),
            F.lit("personal_cumulative").alias("method"),
            F.lit("eligibility-v1").alias("eligibility_policy_version"))

    def test_F_G_H_gate_counts_users_and_skips_original_formula(self):
        import build_global_baseline as global_module
        for case, ready, total in [("F", 5, 5), ("G", 6, 7), ("H", 4, 10)]:
            with self.subTest(case=case), patch.object(global_module, "_compute_global_baseline",
                                                       wraps=global_module._compute_global_baseline) as formula:
                row = global_module.compute_global_baseline(self.personal(ready, total), "c", "2026-W37", "v3").first()
                self.assertEqual(row.eligible_participant_count, ready)
                self.assertEqual(row.status, "ready" if case == "G" else "collecting")
                self.assertEqual(row.value, 102.5 if case == "G" else None)
                self.assertEqual(formula.call_count, 1 if case == "G" else 0)

    def test_duplicate_user_and_other_campaign_cannot_make_six(self):
        from build_global_baseline import compute_global_baseline
        from pyspark.sql import functions as F
        df = self.personal(5)
        with self.assertRaisesRegex(ValueError, "Duplicate Personal"):
            compute_global_baseline(df.unionByName(df.limit(1)), "c", "2026-W37", "v3")
        other = self.personal(6).withColumn("campaign_id", F.lit("other"))
        self.assertEqual(compute_global_baseline(df.unionByName(other), "c", "2026-W37", "v3").first().status, "collecting")

    def test_legacy_snapshot_needs_reevaluation(self):
        from build_global_baseline import compute_global_baseline
        result = compute_global_baseline(self.personal(10).drop("status", "eligibility_policy_version"), "c", "2026-W37", "v3").first()
        self.assertEqual(result.status, "collecting")
        self.assertIsNone(result.value)

    def test_zero_carbon_is_ready_but_nan_is_excluded(self):
        from build_global_baseline import compute_global_baseline
        from pyspark.sql import functions as F
        df = self.personal(6).withColumn("baseline_g_co2e_per_km", F.lit(0.0))
        result = compute_global_baseline(df, "c", "2026-W37", "v3").first()
        self.assertEqual((result.status, result.value), ("ready", 0.0))
        df = df.withColumn("baseline_g_co2e_per_km", F.when(F.col("user_id") == "0", F.lit(float("nan"))).otherwise(F.col("baseline_g_co2e_per_km")))
        result = compute_global_baseline(df, "c", "2026-W37", "v3").first()
        self.assertEqual((result.status, result.eligible_participant_count, result.value), ("collecting", 5, None))

    def test_personal_real_spark_schema_and_gate(self):
        from build_personal_baseline import build_personal_baseline
        from pyspark.sql import functions as F
        df = self.spark.range(2).select(
            F.lit("u").alias("user_id"), F.lit("c").alias("campaign_id"),
            F.when(F.col("id") == 0, "2026-W36").otherwise("2026-W37").alias("week"),
            F.lit(6).alias("trip_count"), F.lit(10000.0).alias("total_distance_m"),
            F.lit(1.2).alias("total_kg_co2e"))
        identities = {"users": [{"user_id": "u", "created_at": "2026-08-31T00:00:00Z"}]}
        rows = build_personal_baseline(df, "v3", identities=identities, commute_scope_verified=True).orderBy("week").collect()
        self.assertEqual([r.status for r in rows], ["collecting", "ready"])
        self.assertIsNone(rows[0].value)
        self.assertEqual(rows[1].value, 120)


if __name__ == "__main__":
    unittest.main()

"""Spark calculation tests for Weekly Personal/Global Baseline.

Local environments without PySpark skip these tests.
Run them in Databricks to validate actual Spark transformations.
"""

from __future__ import annotations

import unittest


try:
    from pyspark.sql import SparkSession
except ModuleNotFoundError:
    PYSPARK_AVAILABLE = False
else:
    PYSPARK_AVAILABLE = True

    from cloud.azure.pipelines.weekly_analysis.helpers.spark_baseline import (
        build_global_baseline,
        build_global_eligibility,
        build_personal_baseline,
        select_personal_ready_users,
    )


ELIGIBILITY_POLICY = {
    "policy_version": "eligibility-v1",
    "personal": {
        "status": {
            "before_eligible": "collecting",
            "when_eligible": "ready",
        },
        "cold_start": {
            "primary_baseline": "population",
            "personal_baseline_enabled": False,
        },
    },
    "global": {
        "participant_rule": {
            "require_personal_status": "ready",
        },
        "minimum_eligible_participants": 6,
        "status": {
            "below_minimum_participants": "collecting",
            "when_eligible": "ready",
        },
    },
}


@unittest.skipUnless(
    PYSPARK_AVAILABLE,
    "PySpark is not installed in this environment",
)
class SparkBaselineTest(unittest.TestCase):

    @classmethod
    @classmethod
    def setUpClass(cls):
        # Databricks에서는 이미 생성된 SparkSession을 재사용한다.
        cls.spark = SparkSession.builder.getOrCreate()

    def test_personal_baseline_uses_prior_week_only(self):
        weekly = self.spark.createDataFrame(
            [
                (
                    "user-1",
                    "campaign-1",
                    "2026-W36",
                    3,
                    1000.0,
                    0.1,
                ),
                (
                    "user-1",
                    "campaign-1",
                    "2026-W37",
                    4,
                    2000.0,
                    0.4,
                ),
            ],
            """
            user_id STRING,
            campaign_id STRING,
            week STRING,
            trip_count LONG,
            total_distance_m DOUBLE,
            total_kg_co2e DOUBLE
            """,
        )

        eligibility = self.spark.createDataFrame(
            [
                (
                    "user-1",
                    "campaign-1",
                    "2026-W36",
                    "ready",
                    "eligibility-v1",
                    7,
                    6,
                    [],
                ),
                (
                    "user-1",
                    "campaign-1",
                    "2026-W37",
                    "ready",
                    "eligibility-v1",
                    14,
                    10,
                    [],
                ),
            ],
            """
            user_id STRING,
            campaign_id STRING,
            week STRING,
            status STRING,
            policy_version STRING,
            observation_days LONG,
            confirmed_trip_count LONG,
            reasons ARRAY<STRING>
            """,
        )

        result = build_personal_baseline(
            weekly,
            eligibility,
            baseline_policy_version="baseline-policy-v4",
            commute_scope_verified=True,
            eligibility_policy=ELIGIBILITY_POLICY,
        )

        rows = {
            row["week"]: row
            for row in result.collect()
        }

        first = rows["2026-W36"]
        second = rows["2026-W37"]

        # 첫 주는 이전 완료 주가 없으므로 Personal 계산 불가
        self.assertEqual(first["status"], "collecting")
        self.assertIsNone(first["baseline_g_co2e_per_km"])

        # W37은 W36만 사용:
        # 0.1 kg = 100 g, 1000 m = 1 km → 100 g/km
        self.assertAlmostEqual(
            second["cumulative_g_co2e"],
            100.0,
        )
        self.assertAlmostEqual(
            second["cumulative_distance_km"],
            1.0,
        )
        self.assertAlmostEqual(
            second["baseline_g_co2e_per_km"],
            100.0,
        )
        self.assertEqual(
            second["method"],
            "personal_cumulative",
        )
        self.assertEqual(
            second["status"],
            "ready",
        )

    def test_personal_ready_users_filters_invalid_rows(self):
        personal = self.spark.createDataFrame(
            [
                (
                    "valid-user",
                    "campaign-1",
                    "2026-W37",
                    100.0,
                    "personal_cumulative",
                    "ready",
                    "eligibility-v1",
                ),
                (
                    "fallback-user",
                    "campaign-1",
                    "2026-W37",
                    None,
                    "population_fallback",
                    "collecting",
                    "eligibility-v1",
                ),
                (
                    "",
                    "campaign-1",
                    "2026-W37",
                    200.0,
                    "personal_cumulative",
                    "ready",
                    "eligibility-v1",
                ),
            ],
            """
            user_id STRING,
            campaign_id STRING,
            week STRING,
            baseline_g_co2e_per_km DOUBLE,
            method STRING,
            status STRING,
            eligibility_policy_version STRING
            """,
        )

        result = select_personal_ready_users(
            personal,
            eligibility_policy=ELIGIBILITY_POLICY,
        )

        users = [
            row["user_id"]
            for row in result.collect()
        ]

        self.assertEqual(
            users,
            ["valid-user"],
        )

    def test_global_eligibility_requires_six_users(self):
        def personal_rows(count):
            return [
                (
                    f"user-{i}",
                    "campaign-1",
                    "2026-W37",
                )
                for i in range(count)
            ]

        personal = self.spark.createDataFrame(
            personal_rows(6),
            """
            user_id STRING,
            campaign_id STRING,
            week STRING
            """,
        )

        ready_five = self.spark.createDataFrame(
            personal_rows(5),
            """
            user_id STRING,
            campaign_id STRING,
            week STRING
            """,
        )

        collecting = build_global_eligibility(
            personal,
            ready_five,
            eligibility_policy=ELIGIBILITY_POLICY,
        ).collect()[0]

        self.assertEqual(
            collecting["eligible_participant_count"],
            5,
        )
        self.assertEqual(
            collecting["status"],
            "collecting",
        )

        ready_six = self.spark.createDataFrame(
            personal_rows(6),
            """
            user_id STRING,
            campaign_id STRING,
            week STRING
            """,
        )

        ready = build_global_eligibility(
            personal,
            ready_six,
            eligibility_policy=ELIGIBILITY_POLICY,
        ).collect()[0]

        self.assertEqual(
            ready["eligible_participant_count"],
            6,
        )
        self.assertEqual(
            ready["status"],
            "ready",
        )

    def test_global_baseline_is_equal_user_mean(self):
        ready = self.spark.createDataFrame(
            [
                (
                    f"user-{i}",
                    "campaign-1",
                    "2026-W37",
                    value,
                )
                for i, value in enumerate(
                    [
                        100.0,
                        200.0,
                        300.0,
                        400.0,
                        500.0,
                        600.0,
                    ],
                    start=1,
                )
            ],
            """
            user_id STRING,
            campaign_id STRING,
            week STRING,
            baseline_g_co2e_per_km DOUBLE
            """,
        )

        eligibility = self.spark.createDataFrame(
            [
                (
                    "campaign-1",
                    "2026-W37",
                    "ready",
                    "eligibility-v1",
                    6,
                )
            ],
            """
            campaign_id STRING,
            week STRING,
            status STRING,
            policy_version STRING,
            eligible_participant_count LONG
            """,
        )

        result = build_global_baseline(
            ready,
            eligibility,
            baseline_policy_version="baseline-policy-v4",
            eligibility_policy=ELIGIBILITY_POLICY,
        ).collect()[0]

        self.assertEqual(
            result["valid_participant_count"],
            6,
        )

        self.assertEqual(
            result["eligible_participant_count"],
            6,
        )

        self.assertAlmostEqual(
            result["baseline_g_co2e_per_km"],
            350.0,
        )

        self.assertAlmostEqual(
            result["value"],
            350.0,
        )

        self.assertEqual(
            result["method"],
            "global_average_of_personal_baseline",
        )

        self.assertEqual(
            result["status"],
            "ready",
        )


if __name__ == "__main__":
    unittest.main()
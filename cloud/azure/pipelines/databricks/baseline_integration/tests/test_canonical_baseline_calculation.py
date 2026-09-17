from pathlib import Path
import sys

import pandas as pd
import pytest

DATABRICKS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DATABRICKS_DIR))

import build_global_baseline as global_calc  # noqa: E402
import build_personal_baseline as personal_calc  # noqa: E402


ELIGIBILITY_V1 = {
    "policy_version": "eligibility-v1",
    "personal": {
        "minimum_observation_days": 7,
        "minimum_confirmed_commute_trips": 6,
        "require_positive_total_distance": True,
        "require_valid_total_carbon": True,
        "status": {"before_eligible": "collecting", "when_eligible": "ready"},
        "cold_start": {"primary_baseline": "population", "personal_baseline_enabled": False},
    },
    "global": {
        "participant_rule": {"require_personal_status": "ready"},
        "minimum_eligible_participants": 6,
        "status": {"below_minimum_participants": "collecting", "when_eligible": "ready"},
    },
}


def test_personal_baseline_uses_only_previous_completed_weeks():
    pdf = pd.DataFrame(
        [
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W37",
                "trip_count": 6,
                "total_kg_co2e": 1.0,
                "total_distance_m": 10_000.0,
            },
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W38",
                "trip_count": 6,
                "total_kg_co2e": 2.0,
                "total_distance_m": 10_000.0,
            },
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W39",
                "trip_count": 6,
                "total_kg_co2e": 1.0,
                "total_distance_m": 20_000.0,
            },
        ]
    )
    identities = {
        "users": [],
        "memberships": [
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "campaign_joined_at": "2026-09-07T00:00:00+00:00",
            }
        ],
    }

    out = personal_calc._compute_personal_baseline(
        pdf,
        "baseline-policy-v4",
        eligibility_policy=ELIGIBILITY_V1,
        identities=identities,
        commute_scope_verified=True,
    )

    first = out.iloc[0]
    second = out.iloc[1]
    third = out.iloc[2]

    assert pd.isna(first["baseline_g_co2e_per_km"])
    assert first["method"] == "population_fallback"
    assert first["status"] == "collecting"
    assert second["status"] == "ready"
    assert second["baseline_g_co2e_per_km"] == pytest.approx(100.0)
    assert third["status"] == "ready"
    assert third["baseline_g_co2e_per_km"] == pytest.approx(150.0)
    assert third["eligibility_policy_version"] == "eligibility-v1"


def test_global_baseline_is_equal_user_average_of_ready_personal(spark):
    values = [100.0, 200.0, 100.0, 200.0, 100.0, 200.0]
    rows = [
        (
            f"u{i + 1}",
            "c1",
            "2026-W39",
            value,
            "personal_cumulative",
            "ready",
            "eligibility-v1",
        )
        for i, value in enumerate(values)
    ]
    rows.append(
        (
            "u7",
            "c1",
            "2026-W39",
            None,
            "population_fallback",
            "collecting",
            "eligibility-v1",
        )
    )
    df = spark.createDataFrame(
        rows,
        [
            "user_id",
            "campaign_id",
            "week",
            "baseline_g_co2e_per_km",
            "method",
            "status",
            "eligibility_policy_version",
        ],
    )

    result = global_calc.compute_global_baseline(
        df,
        campaign_id="c1",
        evaluation_week="2026-W39",
        policy_version="baseline-policy-v4",
        eligibility_policy=ELIGIBILITY_V1,
    ).collect()[0]

    assert result["valid_participant_count"] == 6
    assert result["eligible_participant_count"] == 6
    assert result["status"] == "ready"
    assert result["baseline_g_co2e_per_km"] == pytest.approx(150.0)
    assert result["method"] == "global_average_of_personal_baseline"
    assert result["eligibility_policy_version"] == "eligibility-v1"


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("canopy-baseline-code-check")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()

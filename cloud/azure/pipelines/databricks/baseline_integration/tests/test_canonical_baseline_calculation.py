from pathlib import Path
import sys

import pandas as pd
import pytest

DATABRICKS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DATABRICKS_DIR))

import build_global_baseline as global_calc  # noqa: E402
import build_personal_baseline as personal_calc  # noqa: E402


def test_personal_baseline_uses_only_previous_completed_weeks():
    pdf = pd.DataFrame(
        [
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W37",
                "total_kg_co2e": 1.0,
                "total_distance_m": 10_000.0,
            },
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W38",
                "total_kg_co2e": 2.0,
                "total_distance_m": 10_000.0,
            },
            {
                "user_id": "u1",
                "campaign_id": "c1",
                "week": "2026-W39",
                "total_kg_co2e": 1.0,
                "total_distance_m": 20_000.0,
            },
        ]
    )

    out = personal_calc._compute_personal_baseline(pdf, "baseline-policy-v4")

    first = out.iloc[0]
    second = out.iloc[1]
    third = out.iloc[2]

    assert pd.isna(first["baseline_g_co2e_per_km"])
    assert first["method"] == "population_fallback"
    assert second["baseline_g_co2e_per_km"] == pytest.approx(100.0)
    assert third["baseline_g_co2e_per_km"] == pytest.approx(150.0)


def test_global_baseline_is_equal_user_average_of_ready_personal(spark):
    df = spark.createDataFrame(
        [
            ("u1", "c1", "2026-W39", 100.0, "personal_cumulative"),
            ("u2", "c1", "2026-W39", 200.0, "personal_cumulative"),
            ("u3", "c1", "2026-W39", None, "population_fallback"),
        ],
        ["user_id", "campaign_id", "week", "baseline_g_co2e_per_km", "method"],
    )

    result = global_calc.compute_global_baseline(
        df,
        campaign_id="c1",
        evaluation_week="2026-W39",
        policy_version="baseline-policy-v4",
    ).collect()[0]

    assert result["valid_participant_count"] == 2
    assert result["baseline_g_co2e_per_km"] == pytest.approx(150.0)
    assert result["method"] == "global_average_of_personal_baseline"


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

from behavior_change_policy import classify_behavior_change


def test_changed_when_weekly_intensity_is_below_personal_baseline():
    result = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=80.0,
        personal_baseline_g_per_km=100.0,
        personal_status="ready",
        personal_method="personal_cumulative",
    )
    assert result["status"] == "changed"
    assert result["reduction_g_co2e_per_km"] == 20.0
    assert result["reduction_rate"] == 0.2


def test_equal_or_higher_weekly_intensity_is_no_change():
    equal = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=100.0,
        personal_baseline_g_per_km=100.0,
        personal_status="ready",
        personal_method="personal_cumulative",
    )
    higher = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=120.0,
        personal_baseline_g_per_km=100.0,
        personal_status="ready",
        personal_method="personal_cumulative",
    )
    assert equal["status"] == "no_change"
    assert higher["status"] == "no_change"


def test_personal_baseline_not_ready_is_insufficient_data():
    result = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=50.0,
        personal_baseline_g_per_km=None,
        personal_status="collecting",
        personal_method="population_fallback",
    )
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "personal_baseline_not_ready"


def test_global_or_population_fallback_is_not_used_for_behavior_change():
    result = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=50.0,
        personal_baseline_g_per_km=80.0,
        personal_status="collecting",
        personal_method="population_fallback",
    )
    assert result["status"] == "insufficient_data"


def test_invalid_weekly_metric_is_insufficient_data():
    result = classify_behavior_change(
        weekly_carbon_intensity_g_per_km=None,
        personal_baseline_g_per_km=100.0,
        personal_status="ready",
        personal_method="personal_cumulative",
    )
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "weekly_carbon_intensity_invalid"

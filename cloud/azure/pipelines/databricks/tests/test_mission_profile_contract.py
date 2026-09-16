from pathlib import Path

import build_mission_profile as mod


def test_profile_builds_from_weekly_summary_without_trip_rescan():
    summary = {
        "trip_count": 8,
        "valid_primary_trip_count": 6,
        "invalid_primary_trip_count": 2,
        "ambiguous_primary_trip_count": 1,
        "invalid_segment_primary_trip_count": 1,
        "car_primary_trip_count": 3,
        "short_car_trip_count": 2,
        "transit_primary_trip_count": 1,
        "low_carbon_trip_count": 3,
    }
    profile = mod.build_profile_from_weekly_summary(
        summary,
        user_id="u1",
        campaign_id="c1",
        source_week_start="2026-09-07",
        source_week_end="2026-09-14",
        mission_history_source="none",
    )
    assert profile["valid_trip_count"] == 6
    assert profile["invalid_trip_count"] == 2
    assert profile["invalid_trip_reasons"] == {
        "invalid_segment": 1,
        "primary_mode_tie": 1,
    }
    assert profile["car_primary_trip_count"] == 3
    assert profile["short_car_trip_count"] == 2
    assert profile["transit_primary_trip_count"] == 1
    assert profile["low_carbon_trip_count"] == 3
    assert profile["effective_week_start"] == "2026-09-14"


def test_response_rows_reconstruct_affinity_and_difficulty_separately():
    rows = [
        {
            "week_start": "2026-09-07",
            "week_end": "2026-09-14",
            "bundle_id": "b1",
            "common_target_count": 1,
            "category_id": "challenge",
            "mission_family": "f1",
            "target_count": 1,
            "achievement_rate": 1.0,
            "completed": True,
            "affinity_comparable": True,
            "difficulty_comparable": True,
            "preference_comparable": True,
        },
        {
            "week_start": "2026-09-07",
            "week_end": "2026-09-14",
            "bundle_id": "b1",
            "common_target_count": 1,
            "category_id": "explore",
            "mission_family": "f2",
            "target_count": 1,
            "achievement_rate": 1.0,
            "completed": True,
            "affinity_comparable": False,
            "difficulty_comparable": False,
            "preference_comparable": False,
        },
    ]
    bundles = mod._responses_to_bundles(rows)
    assert len(bundles) == 1
    assert len(bundles[0]["missions"]) == 2
    prefs = mod.compute_category_preferences(bundles)
    assert prefs["challenge"]["positive_evidence_count"] == 1
    assert prefs["explore"]["positive_evidence_count"] == 0
    difficulty = mod.compute_difficulty_state(bundles)
    assert difficulty["last_comparable_mission_count"] == 1
    assert difficulty["last_completed_comparable_count"] == 1


def test_legacy_preference_comparable_remains_backward_compatible():
    rows = [{
        "week_start": "2026-09-07",
        "week_end": "2026-09-14",
        "bundle_id": "legacy",
        "common_target_count": 1,
        "category_id": "habit",
        "mission_family": "legacy-family",
        "target_count": 1,
        "achievement_rate": 1.0,
        "completed": True,
        "preference_comparable": True,
    }]
    bundles = mod._responses_to_bundles(rows)
    assert mod.compute_category_preferences(bundles)["habit"]["positive_evidence_count"] == 1
    assert mod.compute_difficulty_state(bundles)["last_completed_comparable_count"] == 1


def test_history_source_is_part_of_profile_hash_contract():
    base = dict(
        summary={"trip_count": 0},
        user_id="u1",
        campaign_id="c1",
        source_week_start="2026-09-07",
        source_week_end="2026-09-14",
    )
    a = mod.build_profile_from_weekly_summary(**base, mission_history_source="none")
    b = mod.build_profile_from_weekly_summary(**base, mission_history_source="mission_response_gold")
    assert a["profile_hash"] != b["profile_hash"]


def test_weekly_primary_mode_contract_explicitly_rejects_null_mode():
    weekly_path = Path(mod.__file__).with_name("build_weekly_summary.py")
    source = weekly_path.read_text(encoding="utf-8")
    assert 'F.col("effective_mode").isNull()' in source
    assert 'F.col("distance_m").isNull()' in source

from pathlib import Path

import mission_engine

HERE = Path(__file__).resolve().parent
POLICY = mission_engine.load_mission_policy(HERE.parent / "mission_policy.yaml")
WEEK_START = "2026-09-14"


def ready_profile(**overrides):
    base = {
        "profile_status": "ready",
        "profile_version": "mission-profile-v3",
        "profile_hash": "hash-1",
        "source_week_start": "2026-09-07",
        "source_week_end": WEEK_START,
        "valid_trip_count": 10,
        "car_primary_trip_count": 4,
        "short_car_trip_count": 2,
        "transit_primary_trip_count": 2,
        "low_carbon_trip_count": 6,
        "difficulty_state": {},
    }
    base.update(overrides)
    return base


def by_category(missions):
    return {mission["category_id"]: mission for mission in missions}


def test_every_template_has_explicit_completion_rule():
    assert POLICY["catalog"]
    for template in POLICY["catalog"].values():
        assert template["completion_rule"]["metric"] in {
            "qualifying_trip_count",
            "distinct_day_count",
            "distinct_mode_count",
        }


def test_issued_assignment_contains_frozen_completion_rule_and_rendered_copy():
    missions, _, _ = mission_engine.build_bundle_missions(
        ready_profile(), POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    challenge = by_category(missions)["challenge"]
    assert challenge["completion_rule"]["target_count"] == challenge["target_count"]
    assert challenge["completion_rule"]["dedupe_key"] == "trip_id"
    assert challenge["completion_rule"]["time_window"] == "assignment_week"
    assert challenge["completion_rule"]["source"] == "canonical_ready_trip"
    assert "{target_count}" not in challenge["mission_name"]
    assert "{target_count}" not in challenge["mission_description"]


def test_habit_uses_distinct_days_not_raw_trip_count():
    missions, _, _ = mission_engine.build_bundle_missions(
        ready_profile(), POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    habit = by_category(missions)["habit"]
    assert habit["completion_rule"]["metric"] == "distinct_day_count"
    assert habit["progress_unit"] == "일"


def test_explore_is_fixed_one_distinct_mode_and_not_preference_comparable_after_difficulty_rises():
    p = ready_profile(difficulty_state={
        "last_common_target_count": 1,
        "last_comparable_mission_count": 3,
        "last_completed_comparable_count": 3,
    })
    missions, common_target, _ = mission_engine.build_bundle_missions(
        p, POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    explore = by_category(missions)["explore"]
    assert common_target == 2
    assert explore["target_count"] == 1
    assert explore["completion_rule"]["metric"] == "distinct_mode_count"
    assert explore["preference_comparable"] is False


def test_common_target_has_service_safety_cap():
    p = ready_profile(difficulty_state={
        "last_common_target_count": 5,
        "last_comparable_mission_count": 3,
        "last_completed_comparable_count": 3,
    })
    target, reason = mission_engine.common_target_count(p, POLICY)
    assert target == 5
    assert reason == "all_completed_increment"

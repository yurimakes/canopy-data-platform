
import json
import sys
from pathlib import Path

HELPERS_DIR = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS_DIR))

import pytest

import next_week_missions as mod


def base_profile(**overrides):
    profile = {
        "user_id": "user-1",
        "campaign_id": "campaign-1",
        "effective_week_start": "2026-09-21",
        "source_week_start": "2026-09-14",
        "source_week_end": "2026-09-21",
        "profile_version": "mission-profile-v3",
        "profile_status": "ready",
        "profile_hash": "hash-1",
        "category_preferences_json": "{}",
        "difficulty_state_json": "{}",
        "family_capability_json": "{}",
    }
    profile.update(overrides)
    return profile


def test_policy_validation_rejects_missing_category():
    policy = json.loads(json.dumps(mod.DEFAULT_MISSION_POLICY))
    del policy["categories"]["explore"]
    with pytest.raises(mod.MissionPolicyError):
        mod.validate_mission_policy(policy)


def test_load_mission_policy_defaults_are_valid():
    policy = mod.load_mission_policy()
    assert policy["policy_version"] == mod.POLICY_VERSION
    assert set(policy["categories"]) == set(mod.CATEGORY_IDS)


def test_cold_start_profile_marks_all_missions_not_comparable():
    policy = mod.load_mission_policy()
    bundle = mod.build_bundle_for_profile(base_profile(profile_status="collecting"), policy)

    assert len(bundle["missions"]) == 4
    assert bundle["difficulty_reason"] == "cold_start"
    for mission in bundle["missions"]:
        assert mission["affinity_comparable"] is False
        assert mission["difficulty_comparable"] is False
        assert mission["target_count"] == policy["default_common_target_count"]
        assert mission["difficulty_band"] == policy["cold_start_difficulty_band"]


def test_family_capability_full_completion_raises_target_next_week():
    policy = mod.load_mission_policy()
    family = policy["categories"]["easy_win"]["mission_family"]
    profile = base_profile(
        family_capability_json=json.dumps({
            family: {
                "assignment_count": 3,
                "completed_count": 3,
                "last_target_count": 2,
                "last_achievement_rate": 1.0,
                "max_completed_target_count": 2,
            }
        }),
    )
    bundle = mod.build_bundle_for_profile(profile, policy)
    easy_win = next(m for m in bundle["missions"] if m["category_id"] == "easy_win")

    assert easy_win["difficulty_comparable"] is True
    assert easy_win["target_count"] == 3  # 2 -> +1


def test_family_capability_low_completion_lowers_target_next_week():
    policy = mod.load_mission_policy()
    family = policy["categories"]["challenge"]["mission_family"]
    profile = base_profile(
        family_capability_json=json.dumps({
            family: {
                "last_target_count": 2,
                "last_achievement_rate": 0.3,
            }
        }),
    )
    bundle = mod.build_bundle_for_profile(profile, policy)
    challenge = next(m for m in bundle["missions"] if m["category_id"] == "challenge")

    assert challenge["target_count"] == 1  # 2 -> -1


def test_target_count_never_exceeds_policy_max():
    policy = mod.load_mission_policy({"max_target_count": 3})
    family = policy["categories"]["habit"]["mission_family"]
    profile = base_profile(
        family_capability_json=json.dumps({
            family: {"last_target_count": 3, "last_achievement_rate": 1.0},
        }),
    )
    bundle = mod.build_bundle_for_profile(profile, policy)
    habit = next(m for m in bundle["missions"] if m["category_id"] == "habit")
    assert habit["target_count"] == 3  # clipped at max


def test_category_preference_history_enables_affinity_comparable():
    policy = mod.load_mission_policy()
    profile = base_profile(
        category_preferences_json=json.dumps({
            "challenge": {"positive_evidence_count": 2, "preference_share": 0.4},
        }),
    )
    bundle = mod.build_bundle_for_profile(profile, policy)
    challenge = next(m for m in bundle["missions"] if m["category_id"] == "challenge")
    other = next(m for m in bundle["missions"] if m["category_id"] == "habit")

    assert challenge["affinity_comparable"] is True
    assert other["affinity_comparable"] is False


def test_malformed_json_fields_fall_back_to_cold_start_not_error():
    policy = mod.load_mission_policy()
    profile = base_profile(
        category_preferences_json="not-json",
        family_capability_json="[]",
    )
    bundle = mod.build_bundle_for_profile(profile, policy)
    assert len(bundle["missions"]) == 4
    assert all(m["difficulty_comparable"] is False for m in bundle["missions"])


def test_missing_required_profile_field_fails_closed():
    policy = mod.load_mission_policy()
    profile = base_profile()
    del profile["user_id"]
    with pytest.raises(mod.MissionPolicyError):
        mod.build_bundle_for_profile(profile, policy)


def test_bundle_shape_matches_output_columns():
    policy = mod.load_mission_policy()
    bundle = mod.build_bundle_for_profile(base_profile(), policy)
    assert set(bundle.keys()) == set(mod.OUTPUT_COLUMNS)


def test_missing_canonical_policy_file_falls_back_to_default(tmp_path):
    missing = tmp_path / "does-not-exist.yaml"
    policy = mod.load_mission_policy_file(str(missing))
    assert policy["policy_version"] == mod.POLICY_VERSION
    assert set(policy["categories"]) == set(mod.CATEGORY_IDS)


_VALID_POLICY_YAML = """
policy_version: mission-policy-v3.2
default_common_target_count: 3
min_target_count: 1
max_target_count: 5
cold_start_difficulty_band: starter
categories:
  challenge:
    category_label: 도전형
    mission_family: car_to_transit
    mission_template_id: tmpl-challenge-car-to-transit
    mission_name: 대중교통으로 출퇴근하기
    mission_description: 설명
    progress_unit: trip
    difficulty_band: standard
    completion_rule: {metric: qualifying_trip_count, accepted_primary_modes: [bus, rail]}
  habit:
    category_label: 꾸준형
    mission_family: low_carbon_habit
    mission_template_id: tmpl-habit-low-carbon
    mission_name: 저탄소 이동 유지하기
    mission_description: 설명
    progress_unit: day
    difficulty_band: standard
    completion_rule: {metric: distinct_day_count, accepted_primary_modes: [walk, bike, bus, rail]}
  easy_win:
    category_label: 쉬운 성공형
    mission_family: short_car_to_active
    mission_template_id: tmpl-easywin-short-car-to-active
    mission_name: 짧은 거리는 걷거나 자전거로
    mission_description: 설명
    progress_unit: trip
    difficulty_band: easy
    completion_rule: {metric: qualifying_trip_count, accepted_primary_modes: [walk, bike], max_trip_distance_km: 2.0}
  explore:
    category_label: 탐험형
    mission_family: mode_explorer
    mission_template_id: tmpl-explore-mode-explorer
    mission_name: 새로운 이동수단 시도하기
    mission_description: 설명
    progress_unit: mode
    difficulty_band: easy
    completion_rule: {metric: distinct_mode_count, accepted_primary_modes: [walk, bike, bus, rail]}
"""


def test_existing_canonical_policy_file_overrides_defaults(tmp_path):
    policy_file = tmp_path / "mission_policy.yaml"
    policy_file.write_text(_VALID_POLICY_YAML, encoding="utf-8")

    policy = mod.load_mission_policy_file(str(policy_file))
    assert policy["default_common_target_count"] == 3


def test_invalid_canonical_policy_file_fails_closed(tmp_path):
    policy_file = tmp_path / "mission_policy.yaml"
    policy_file.write_text(_VALID_POLICY_YAML.replace("  explore:\n", "  explore_renamed:\n"), encoding="utf-8")

    with pytest.raises(mod.MissionPolicyError):
        mod.load_mission_policy_file(str(policy_file))


def test_env_var_overrides_canonical_path(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist.yaml"
    monkeypatch.setenv("CANOPY_MISSION_POLICY_PATH", str(missing))
    policy = mod.load_mission_policy_file()
    assert policy["policy_version"] == mod.POLICY_VERSION

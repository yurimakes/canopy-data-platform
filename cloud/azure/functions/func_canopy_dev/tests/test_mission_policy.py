import copy
from pathlib import Path

import mission_engine

HERE = Path(__file__).resolve().parent
POLICY = mission_engine.load_mission_policy(HERE.parent / "mission_policy.yaml")
WEEK_START = "2026-09-14"
WEEK_END = "2026-09-21"
NOW = "2026-09-14T00:00:00+00:00"


def profile(**overrides):
    base = {
        "profile_status": "ready",
        "profile_version": "mission-profile-v3",
        "profile_hash": "hash-1",
        "source_week_start": "2026-09-07",
        "source_week_end": WEEK_START,
        "valid_trip_count": 10,
        "car_primary_trip_count": 4,
        "car_ratio": .4,
        "short_car_trip_count": 2,
        "short_car_share": .5,
        "transit_primary_trip_count": 3,
        "low_carbon_trip_count": 6,
        "difficulty_state": {},
    }
    base.update(overrides)
    return base


class MemoryRepo:
    def __init__(self, profile_doc=None):
        self.profile_doc = profile_doc
        self.bundles = {}

    @staticmethod
    def pk(campaign_id, user_id):
        return f"{campaign_id}:{user_id}"

    def get_latest_profile(self, campaign_id, user_id):
        return self.profile_doc

    def get_bundle(self, campaign_id, user_id, week_start):
        key = mission_engine.bundle_id(campaign_id, user_id, week_start)
        return copy.deepcopy(self.bundles.get(key))

    def create_bundle(self, item):
        self.bundles.setdefault(item["id"], copy.deepcopy(item))
        return copy.deepcopy(self.bundles[item["id"]])


def by_category(missions):
    return {mission["category_id"]: mission for mission in missions}


def test_01_02_03_04_cold_start_assigns_four_categories_without_user_choice():
    missions, common_target, _ = mission_engine.build_bundle_missions(
        None, POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    assert len(missions) == 4
    assert {m["category_id"] for m in missions} == {"challenge", "habit", "easy_win", "explore"}
    assert all(m["mission_template_id"].endswith("starter") for m in missions)
    assert common_target == 1
    assert all(m["target_count"] == 1 for m in missions)
    assert all(m["preference_comparable"] is True for m in missions)


def test_05_06_behavior_fit_changes_challenge_template():
    short = by_category(mission_engine.build_bundle_missions(
        profile(short_car_trip_count=3, car_primary_trip_count=5), POLICY,
        campaign_id="c1", user_id="u1", week_start=WEEK_START
    )[0])
    assert short["challenge"]["mission_template_id"] == "challenge_short_car_to_active"

    no_short = by_category(mission_engine.build_bundle_missions(
        profile(short_car_trip_count=0, car_primary_trip_count=5), POLICY,
        campaign_id="c1", user_id="u1", week_start=WEEK_START
    )[0])
    assert no_short["challenge"]["mission_template_id"] == "challenge_car_to_transit"


def test_07_08_09_other_categories_use_behavior_fit_templates():
    missions = by_category(mission_engine.build_bundle_missions(
        profile(short_car_trip_count=2, car_primary_trip_count=4, low_carbon_trip_count=6),
        POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )[0])
    assert missions["habit"]["mission_template_id"] == "habit_low_carbon_maintain"
    assert missions["easy_win"]["mission_template_id"] == "easy_short_active"
    assert missions["explore"]["mission_template_id"] == "explore_active"


def test_10_all_comparable_completed_raises_next_common_target():
    p = profile(difficulty_state={
        "last_common_target_count": 1,
        "last_comparable_mission_count": 4,
        "last_completed_comparable_count": 4,
    })
    target, reason = mission_engine.common_target_count(p, POLICY)
    assert target == 2
    assert reason == "all_completed_increment"


def test_11_none_completed_decreases_but_never_below_one():
    p = profile(difficulty_state={
        "last_common_target_count": 1,
        "last_comparable_mission_count": 4,
        "last_completed_comparable_count": 0,
    })
    assert mission_engine.common_target_count(p, POLICY)[0] == 1


def test_12_partial_completion_holds_common_target():
    p = profile(difficulty_state={
        "last_common_target_count": 2,
        "last_comparable_mission_count": 4,
        "last_completed_comparable_count": 2,
    })
    assert mission_engine.common_target_count(p, POLICY)[0] == 2


def test_13_opportunity_cap_makes_that_mission_noncomparable():
    p = profile(
        short_car_trip_count=1,
        difficulty_state={
            "last_common_target_count": 2,
            "last_comparable_mission_count": 4,
            "last_completed_comparable_count": 4,
        },
    )
    missions, common_target, _ = mission_engine.build_bundle_missions(
        p, POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    challenge = by_category(missions)["challenge"]
    assert common_target == 3
    assert challenge["target_count"] == 1
    assert challenge["preference_comparable"] is False


def test_14_category_does_not_make_objective_difficulty_harder():
    missions, common_target, _ = mission_engine.build_bundle_missions(
        profile(), POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    comparable_targets = {m["target_count"] for m in missions if m["preference_comparable"]}
    assert comparable_targets == {common_target}


def test_15_assignment_ids_are_distinct_per_category():
    missions, _, _ = mission_engine.build_bundle_missions(
        None, POLICY, campaign_id="c1", user_id="u1", week_start=WEEK_START
    )
    assert len({m["assignment_id"] for m in missions}) == 4


def test_16_bundle_id_is_deterministic():
    assert mission_engine.bundle_id("c1", "u1", WEEK_START) == mission_engine.bundle_id("c1", "u1", WEEK_START)


def test_17_bundle_issue_is_idempotent_and_frozen():
    repo = MemoryRepo(profile())
    first = mission_engine.issue_weekly_bundle(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW
    )
    repo.profile_doc["short_car_trip_count"] = 0
    second = mission_engine.issue_weekly_bundle(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END,
        now_iso="2026-09-15T00:00:00+00:00"
    )
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["bundle"] == second["bundle"]


def test_18_no_profile_is_supported_instead_of_collecting_only():
    repo = MemoryRepo(None)
    result = mission_engine.get_week_state(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW
    )
    assert result["status"] == "assigned"
    assert result["bundle"]["profile_status_at_issue"] == "cold_start"


def test_19_inactive_template_is_not_assigned():
    changed = copy.deepcopy(POLICY)
    changed["catalog"]["challenge_short_car_to_active"]["status"] = "retired"
    missions = by_category(mission_engine.build_bundle_missions(
        profile(short_car_trip_count=3, car_primary_trip_count=5), changed,
        campaign_id="c1", user_id="u1", week_start=WEEK_START
    )[0])
    assert missions["challenge"]["mission_template_id"] == "challenge_car_to_transit"


def test_20_get_state_returns_same_weekly_bundle():
    repo = MemoryRepo(None)
    first = mission_engine.get_week_state(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW
    )
    second = mission_engine.get_week_state(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW
    )
    assert first["bundle"]["bundle_id"] == second["bundle"]["bundle_id"]
    assert first["bundle"]["missions"] == second["bundle"]["missions"]

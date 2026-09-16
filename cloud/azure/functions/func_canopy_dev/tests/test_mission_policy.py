import copy
from pathlib import Path

import pytest
import mission_engine

HERE = Path(__file__).resolve().parent
POLICY = mission_engine.load_mission_policy(HERE.parent / "mission_policy.yaml")
WEEK_START = "2026-09-14"
WEEK_END = "2026-09-21"
NOW = "2026-09-14T00:00:00+00:00"


def profile(**overrides):
    base = {
        "profile_status": "ready",
        "profile_version": "mission-profile-v2",
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
        "category_preferences": {},
        "family_capability": {},
    }
    base.update(overrides)
    return base


class MemoryRepo:
    def __init__(self, profile_doc=None):
        self.profile_doc = profile_doc
        self.offers = {}
        self.assignments = {}

    @staticmethod
    def pk(campaign_id, user_id):
        return f"{campaign_id}:{user_id}"

    def get_latest_profile(self, campaign_id, user_id):
        return self.profile_doc

    def get_offer_set(self, campaign_id, user_id, week_start):
        return copy.deepcopy(self.offers.get(mission_engine.offer_set_id(campaign_id, user_id, week_start)))

    def create_offer_set(self, item):
        self.offers.setdefault(item["id"], copy.deepcopy(item))
        return copy.deepcopy(self.offers[item["id"]])

    def get_assignment(self, campaign_id, user_id, week_start):
        return copy.deepcopy(self.assignments.get(mission_engine.assignment_id(campaign_id, user_id, week_start)))

    def create_assignment(self, item):
        self.assignments.setdefault(item["id"], copy.deepcopy(item))
        return copy.deepcopy(self.assignments[item["id"]])

    def mark_offer_selected(self, offer, mission_template_id, selected_at):
        stored = self.offers[offer["id"]]
        if not stored.get("selected_mission_template_id"):
            stored["selected_mission_template_id"] = mission_template_id
            stored["selected_at"] = selected_at
        return copy.deepcopy(stored)


def by_category(candidates):
    return {candidate["category_id"]: candidate for candidate in candidates}


def test_01_02_03_cold_start_offers_all_categories_with_equal_priors_and_minimum_target():
    candidates = mission_engine.build_offer_candidates(None, POLICY, week_start=WEEK_START)
    assert len(candidates) == 4
    assert {item["category_id"] for item in candidates} == {"challenge", "habit", "easy_win", "explore"}
    assert all(item["preference_score"] == .5 for item in candidates)
    assert all(item["target_count"] == 1 for item in candidates)
    assert candidates[0]["category_id"] == "challenge"
    assert candidates[0]["is_recommended"] is True


def test_04_stale_behavior_profile_keeps_preference_but_uses_starter_templates():
    p = profile(
        source_week_end="2026-09-07",
        category_preferences={
            "habit": {"alpha": 5.0, "beta": 1.0},
            "challenge": {"alpha": 1.0, "beta": 4.0},
        },
    )
    candidates = mission_engine.build_offer_candidates(p, POLICY, week_start=WEEK_START)
    assert candidates[0]["category_id"] == "habit"
    assert all(item["mission_template_id"].endswith("starter") for item in candidates)


def test_05_06_behavior_fit_changes_challenge_template():
    short = by_category(mission_engine.build_offer_candidates(
        profile(short_car_trip_count=3, car_primary_trip_count=5), POLICY, week_start=WEEK_START
    ))
    assert short["challenge"]["mission_template_id"] == "challenge_short_car_to_active"

    no_short = by_category(mission_engine.build_offer_candidates(
        profile(short_car_trip_count=0, car_primary_trip_count=5), POLICY, week_start=WEEK_START
    ))
    assert no_short["challenge"]["mission_template_id"] == "challenge_car_to_transit"


def test_07_08_09_other_categories_choose_behavior_fit_templates():
    candidates = by_category(mission_engine.build_offer_candidates(
        profile(short_car_trip_count=2, car_primary_trip_count=4, low_carbon_trip_count=6),
        POLICY,
        week_start=WEEK_START,
    ))
    assert candidates["habit"]["mission_template_id"] == "habit_low_carbon_maintain"
    assert candidates["easy_win"]["mission_template_id"] == "easy_short_active_once"
    assert candidates["explore"]["mission_template_id"] == "explore_active"


def test_10_11_12_13_adaptive_family_target_rules():
    base = profile(short_car_trip_count=4)
    template = POLICY["catalog"]["challenge_short_car_to_active"]

    completed = copy.deepcopy(base)
    completed["family_capability"] = {"short_car_to_active": {"last_target_count": 2, "last_achievement_rate": 1.0}}
    assert mission_engine.compute_target_count(template, completed, POLICY, week_start=WEEK_START)[0] == 3

    partial = copy.deepcopy(base)
    partial["family_capability"] = {"short_car_to_active": {"last_target_count": 2, "last_achievement_rate": .5}}
    assert mission_engine.compute_target_count(template, partial, POLICY, week_start=WEEK_START)[0] == 2

    zero = copy.deepcopy(base)
    zero["family_capability"] = {"short_car_to_active": {"last_target_count": 1, "last_achievement_rate": 0.0}}
    assert mission_engine.compute_target_count(template, zero, POLICY, week_start=WEEK_START)[0] == 1

    capped = profile(short_car_trip_count=2)
    capped["family_capability"] = {"short_car_to_active": {"last_target_count": 3, "last_achievement_rate": 1.0}}
    assert mission_engine.compute_target_count(template, capped, POLICY, week_start=WEEK_START)[0] == 2


def test_14_15_preference_ranking_and_equal_prior_tie_are_deterministic():
    p = profile(category_preferences={
        "habit": {"alpha": 4.0, "beta": 1.0},
        "challenge": {"alpha": 2.0, "beta": 3.0},
        "easy_win": {"alpha": 2.0, "beta": 2.0},
        "explore": {"alpha": 1.0, "beta": 4.0},
    })
    ranked = mission_engine.build_offer_candidates(p, POLICY, week_start=WEEK_START)
    assert ranked[0]["category_id"] == "habit"
    assert ranked[0]["is_recommended"] is True

    equal = mission_engine.build_offer_candidates(profile(), POLICY, week_start=WEEK_START)
    assert [item["category_id"] for item in equal] == ["challenge", "habit", "easy_win", "explore"]


def test_16_offer_set_is_idempotent_and_frozen():
    repo = MemoryRepo(profile())
    first = mission_engine.issue_offer_set(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )
    repo.profile_doc["category_preferences"] = {"habit": {"alpha": 99.0, "beta": 1.0}}
    second = mission_engine.issue_offer_set(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso="2026-09-15T00:00:00+00:00",
    )
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["offer_set"] == second["offer_set"]


def test_17_selection_creates_one_active_assignment():
    repo = MemoryRepo(None)
    offer_result = mission_engine.issue_offer_set(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )
    offer = offer_result["offer_set"]
    selected = next(item for item in offer["candidates"] if item["category_id"] == "explore")
    result = mission_engine.select_mission(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END,
        requested_offer_set_id=offer["offer_set_id"],
        mission_template_id=selected["mission_template_id"], now_iso=NOW,
    )
    assert result["status"] == "assigned"
    assert result["assignment"]["category_id"] == "explore"
    assert len(repo.assignments) == 1


def test_18_second_different_selection_cannot_replace_first_assignment():
    repo = MemoryRepo(None)
    offer = mission_engine.issue_offer_set(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )["offer_set"]
    first, second = offer["candidates"][0], offer["candidates"][1]
    mission_engine.select_mission(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END,
        requested_offer_set_id=offer["offer_set_id"], mission_template_id=first["mission_template_id"], now_iso=NOW,
    )
    result = mission_engine.select_mission(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END,
        requested_offer_set_id=offer["offer_set_id"], mission_template_id=second["mission_template_id"], now_iso=NOW,
    )
    assert result["selection_conflict"] is True
    assert result["assignment"]["mission_template_id"] == first["mission_template_id"]


def test_19_invalid_selection_is_rejected():
    repo = MemoryRepo(None)
    offer = mission_engine.issue_offer_set(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )["offer_set"]
    with pytest.raises(mission_engine.MissionSelectionError):
        mission_engine.select_mission(
            repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END,
            requested_offer_set_id=offer["offer_set_id"], mission_template_id="not-offered", now_iso=NOW,
        )


def test_20_get_state_returns_assignment_after_selection():
    repo = MemoryRepo(None)
    offer = mission_engine.get_week_state(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )["offer_set"]
    chosen = offer["candidates"][0]
    mission_engine.select_mission(
        repo, POLICY, user_id="u1", campaign_id="c1", week_start=WEEK_START, week_end=WEEK_END,
        requested_offer_set_id=offer["offer_set_id"], mission_template_id=chosen["mission_template_id"], now_iso=NOW,
    )
    state = mission_engine.get_week_state(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start=WEEK_START, week_end=WEEK_END, now_iso=NOW,
    )
    assert state["status"] == "assigned"
    assert state["assignment"]["mission_template_id"] == chosen["mission_template_id"]

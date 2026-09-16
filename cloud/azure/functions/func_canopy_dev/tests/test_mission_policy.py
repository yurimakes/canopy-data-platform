import copy
from pathlib import Path
import mission_engine

HERE = Path(__file__).resolve().parent
POLICY = mission_engine.load_mission_policy(HERE.parent / "mission_policy.yaml")


def profile(**overrides):
    base = {
        "profile_status": "ready",
        "profile_version": "mission-profile-v1",
        "profile_hash": "hash-1",
        "source_week_start": "2026-09-07",
        "source_week_end": "2026-09-14",
        "valid_trip_count": 10,
        "car_primary_trip_count": 0,
        "car_ratio": 0.0,
        "short_car_trip_count": 0,
        "short_car_share": None,
        "low_carbon_trip_count": 10,
        "previous_mission_family": None,
        "previous_target_count": None,
        "previous_achievement_rate": None,
    }
    base.update(overrides)
    return base


CASES = [
    ("01_collecting", profile(profile_status="collecting", valid_trip_count=0, car_ratio=None), "collecting", None, None),
    ("02_short_majority", profile(car_primary_trip_count=8, car_ratio=.8, short_car_trip_count=6, short_car_share=.75, low_carbon_trip_count=2), "assigned", "short_car_to_active", 1),
    ("03_short_boundary_exact_half", profile(car_primary_trip_count=8, car_ratio=.8, short_car_trip_count=4, short_car_share=.5, low_carbon_trip_count=2), "assigned", "car_to_transit", 1),
    ("04_car_boundary_exact_half", profile(car_primary_trip_count=5, car_ratio=.5, short_car_trip_count=4, short_car_share=.8, low_carbon_trip_count=5), "assigned", "low_carbon_maintain", 5),
    ("05_just_over_both", profile(car_primary_trip_count=6, car_ratio=.51, short_car_trip_count=4, short_car_share=.51, low_carbon_trip_count=4), "assigned", "short_car_to_active", 1),
    ("06_car_over_short_under", profile(car_primary_trip_count=6, car_ratio=.51, short_car_trip_count=2, short_car_share=.49, low_carbon_trip_count=4), "assigned", "car_to_transit", 1),
    ("07_zero_car_nullable_short_share", profile(car_primary_trip_count=0, car_ratio=0.0, short_car_trip_count=0, short_car_share=None, low_carbon_trip_count=10), "assigned", "low_carbon_maintain", 10),
    ("08_all_transit_maintain", profile(car_primary_trip_count=0, car_ratio=0.0, short_car_share=None, low_carbon_trip_count=5, valid_trip_count=5), "assigned", "low_carbon_maintain", 5),
    ("09_short_completed_increment", profile(car_primary_trip_count=5, car_ratio=.8, short_car_trip_count=4, short_car_share=.8, low_carbon_trip_count=1, previous_mission_family="short_car_to_active", previous_target_count=1, previous_achievement_rate=1.0), "assigned", "short_car_to_active", 2),
    ("10_short_partial_hold", profile(car_primary_trip_count=6, car_ratio=.8, short_car_trip_count=5, short_car_share=.8, previous_mission_family="short_car_to_active", previous_target_count=2, previous_achievement_rate=.5), "assigned", "short_car_to_active", 2),
    ("11_short_zero_decrement", profile(car_primary_trip_count=6, car_ratio=.8, short_car_trip_count=5, short_car_share=.8, previous_mission_family="short_car_to_active", previous_target_count=2, previous_achievement_rate=0.0), "assigned", "short_car_to_active", 1),
    ("12_short_opportunity_cap", profile(car_primary_trip_count=5, car_ratio=.8, short_car_trip_count=3, short_car_share=.8, previous_mission_family="short_car_to_active", previous_target_count=4, previous_achievement_rate=1.0), "assigned", "short_car_to_active", 3),
    ("13_transit_completed_increment", profile(car_primary_trip_count=5, car_ratio=.8, short_car_trip_count=1, short_car_share=.2, previous_mission_family="car_to_transit", previous_target_count=2, previous_achievement_rate=1.0), "assigned", "car_to_transit", 3),
    ("14_transit_minimum_one", profile(car_primary_trip_count=5, car_ratio=.8, short_car_trip_count=1, short_car_share=.2, previous_mission_family="car_to_transit", previous_target_count=1, previous_achievement_rate=0.0), "assigned", "car_to_transit", 1),
    ("15_family_changed_resets", profile(car_primary_trip_count=5, car_ratio=.8, short_car_trip_count=1, short_car_share=.2, previous_mission_family="short_car_to_active", previous_target_count=4, previous_achievement_rate=1.0), "assigned", "car_to_transit", 1),
    ("16_maintain_ignores_escalation", profile(car_primary_trip_count=2, car_ratio=.2, short_car_trip_count=1, short_car_share=.5, low_carbon_trip_count=7, previous_mission_family="low_carbon_maintain", previous_target_count=6, previous_achievement_rate=1.0), "assigned", "low_carbon_maintain", 7),
    ("17_car_majority_missing_short_share", profile(car_primary_trip_count=6, car_ratio=.6, short_car_trip_count=0, short_car_share=None, low_carbon_trip_count=4), "collecting", None, None),
    ("18_short_opportunity_one_cap", profile(car_primary_trip_count=1, valid_trip_count=1, car_ratio=1.0, short_car_trip_count=1, short_car_share=1.0, low_carbon_trip_count=0, previous_mission_family="short_car_to_active", previous_target_count=1, previous_achievement_rate=1.0), "assigned", "short_car_to_active", 1),
    ("19_same_family_missing_result_resets", profile(car_primary_trip_count=6, car_ratio=.8, short_car_trip_count=1, short_car_share=.2, previous_mission_family="car_to_transit", previous_target_count=3, previous_achievement_rate=None), "assigned", "car_to_transit", 1),
    ("20_ratio_boundary_precision", profile(car_primary_trip_count=5001, valid_trip_count=10000, car_ratio=.5001, short_car_trip_count=2500, short_car_share=2500/5001, low_carbon_trip_count=4999), "assigned", "car_to_transit", 1),
]


def test_twenty_policy_cases():
    assert len(CASES) == 20
    for name, p, expected_status, expected_template, expected_target in CASES:
        decision = mission_engine.decide_mission(p, POLICY)
        assert decision.status == expected_status, name
        assert decision.template_id == expected_template, name
        assert decision.target_count == expected_target, name


class MemoryRepo:
    def __init__(self, profile_doc):
        self.profile_doc = profile_doc
        self.assignments = {}

    @staticmethod
    def pk(campaign_id, user_id):
        return f"{campaign_id}:{user_id}"

    def get_latest_profile(self, campaign_id, user_id):
        return self.profile_doc

    def get_assignment(self, campaign_id, user_id, week_start):
        return self.assignments.get(mission_engine.assignment_id(campaign_id, user_id, week_start))

    def create_assignment(self, item):
        self.assignments.setdefault(item["id"], copy.deepcopy(item))
        return copy.deepcopy(self.assignments[item["id"]])


def test_assignment_is_idempotent_and_frozen():
    p = profile(
        car_primary_trip_count=8,
        car_ratio=.8,
        short_car_trip_count=6,
        short_car_share=.75,
        low_carbon_trip_count=2,
    )
    repo = MemoryRepo(p)
    first = mission_engine.assign_for_week(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start="2026-09-14", week_end="2026-09-21", now_iso="2026-09-14T00:00:00+00:00"
    )
    first_assignment = copy.deepcopy(first["assignment"])
    repo.profile_doc["car_ratio"] = 0.0
    repo.profile_doc["low_carbon_trip_count"] = 10
    second = mission_engine.assign_for_week(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start="2026-09-14", week_end="2026-09-21", now_iso="2026-09-15T00:00:00+00:00"
    )
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert second["assignment"] == first_assignment


def test_assignment_rejects_stale_profile():
    p = profile(source_week_end="2026-09-07")
    repo = MemoryRepo(p)
    result = mission_engine.assign_for_week(
        repo, POLICY, user_id="u1", campaign_id="c1",
        week_start="2026-09-14", week_end="2026-09-21", now_iso="2026-09-14T00:00:00+00:00"
    )
    assert result["status"] == "collecting"
    assert result["reason"] == "latest_profile_is_not_previous_completed_week"

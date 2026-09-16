import build_mission_profile as mod


def trip(*segments):
    return {"segments": [{"model_prediction": mode, "distance_m": distance} for mode, distance in segments]}


def bundle(week, completed_categories=(), common_target=1, noncomparable_categories=()):
    missions = []
    for category in ("challenge", "habit", "easy_win", "explore"):
        completed = category in set(completed_categories)
        missions.append({
            "category_id": category,
            "mission_family": f"family_{category}",
            "target_count": common_target,
            "achievement_rate": 1.0 if completed else 0.0,
            "completed": completed,
            "preference_comparable": category not in set(noncomparable_categories),
        })
    return {
        "week_start": week,
        "created_at": f"{week}T00:00:00Z",
        "common_target_count": common_target,
        "missions": missions,
    }


def test_primary_mode_uses_unique_max_distance():
    mode, total, reason = mod.derive_trip_primary_mode(trip(("walk", 300), ("bus", 2700)))
    assert mode == "bus"
    assert total == 3000
    assert reason is None


def test_primary_mode_tie_is_not_arbitrarily_broken():
    mode, total, reason = mod.derive_trip_primary_mode(trip(("car", 1000), ("bus", 1000)))
    assert mode is None
    assert total == 2000
    assert reason == "primary_mode_tie"


def test_profile_counts_primary_modes_and_short_car():
    p = mod.build_profile_from_trips(
        [trip(("car", 1500)), trip(("car", 3000)), trip(("bus", 4000)), trip(("walk", 900))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14"
    )
    assert p["profile_status"] == "ready"
    assert p["valid_trip_count"] == 4
    assert p["car_primary_trip_count"] == 2
    assert p["car_ratio"] == .5
    assert p["short_car_trip_count"] == 1
    assert p["short_car_share"] == .5
    assert p["transit_primary_trip_count"] == 1
    assert p["low_carbon_trip_count"] == 2


def test_zero_car_keeps_nullable_short_share_but_ready():
    p = mod.build_profile_from_trips(
        [trip(("walk", 900)), trip(("rail", 5000))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14"
    )
    assert p["profile_status"] == "ready"
    assert p["car_ratio"] == 0.0
    assert p["short_car_share"] is None


def test_noncompletion_does_not_reduce_preference():
    prefs = mod.compute_category_preferences([
        bundle("2026-09-01", completed_categories=("habit",)),
        bundle("2026-09-08", completed_categories=()),
    ])
    assert prefs["habit"]["positive_evidence_count"] == 1
    assert prefs["challenge"]["positive_evidence_count"] == 0
    assert prefs["habit"]["preference_share"] > prefs["challenge"]["preference_share"]


def test_multiple_completed_categories_all_receive_positive_evidence():
    prefs = mod.compute_category_preferences([
        bundle("2026-09-01", completed_categories=("challenge", "explore")),
    ])
    assert prefs["challenge"]["positive_evidence_count"] == 1
    assert prefs["explore"]["positive_evidence_count"] == 1
    assert prefs["habit"]["positive_evidence_count"] == 0


def test_noncomparable_completed_mission_does_not_change_preference():
    prefs = mod.compute_category_preferences([
        bundle("2026-09-01", completed_categories=("challenge",), noncomparable_categories=("challenge",)),
    ])
    assert prefs["challenge"]["completed_count"] == 1
    assert prefs["challenge"]["positive_evidence_count"] == 0


def test_no_completed_mission_keeps_equal_prior_shares():
    prefs = mod.compute_category_preferences([bundle("2026-09-01")])
    assert {round(v["preference_share"], 6) for v in prefs.values()} == {0.25}


def test_difficulty_state_uses_latest_bundle_comparable_results():
    state = mod.compute_difficulty_state([
        bundle("2026-09-01", completed_categories=("challenge",), common_target=1),
        bundle("2026-09-08", completed_categories=("challenge", "habit"), common_target=2),
    ])
    assert state["last_common_target_count"] == 2
    assert state["last_comparable_mission_count"] == 4
    assert state["last_completed_comparable_count"] == 2


def test_family_capability_is_separate_from_preference():
    state = mod.compute_family_capability([
        bundle("2026-09-01", completed_categories=("challenge",), common_target=1),
        bundle("2026-09-08", completed_categories=("challenge",), common_target=2),
    ])
    assert state["family_challenge"]["assignment_count"] == 2
    assert state["family_challenge"]["completed_count"] == 2
    assert state["family_challenge"]["max_completed_target_count"] == 2


def test_no_trips_but_mission_history_is_history_only():
    p = mod.build_profile_from_trips(
        [], user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14",
        bundle_history=[bundle("2026-09-01", completed_categories=("challenge",))],
    )
    assert p["profile_status"] == "history_only"
    assert p["category_preferences"]["challenge"]["preference_share"] > .25


def test_profile_combines_behavior_preference_and_difficulty():
    p = mod.build_profile_from_trips(
        [trip(("car", 1500)), trip(("bus", 3000))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14",
        bundle_history=[bundle("2026-09-01", completed_categories=("habit",), common_target=1)],
    )
    assert p["profile_status"] == "ready"
    assert p["car_ratio"] == .5
    assert p["category_preferences"]["habit"]["positive_evidence_count"] == 1
    assert p["difficulty_state"]["last_common_target_count"] == 1


def test_campaign_timezone_week_bounds_are_converted_to_utc():
    start, end = mod._utc_week_bounds("2026-09-07", "2026-09-14", "Asia/Seoul")
    assert start.startswith("2026-09-06T15:00:00+00:00")
    assert end.startswith("2026-09-13T15:00:00+00:00")

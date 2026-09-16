import build_mission_profile as mod


def trip(*segments):
    return {"segments": [{"model_prediction": mode, "distance_m": distance} for mode, distance in segments]}


def offer(week, selected_category=None):
    candidates = [
        {"category_id": "challenge", "mission_template_id": "m_challenge"},
        {"category_id": "habit", "mission_template_id": "m_habit"},
        {"category_id": "easy_win", "mission_template_id": "m_easy"},
        {"category_id": "explore", "mission_template_id": "m_explore"},
    ]
    selected = None
    if selected_category:
        selected = next(c["mission_template_id"] for c in candidates if c["category_id"] == selected_category)
    return {"week_start": week, "candidates": candidates, "selected_mission_template_id": selected}


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
    trips = [
        trip(("car", 1500)),
        trip(("car", 3000)),
        trip(("bus", 4000)),
        trip(("walk", 900)),
    ]
    p = mod.build_profile_from_trips(
        trips, user_id="u1", campaign_id="c1",
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
    assert p["low_carbon_trip_count"] == 2


def test_only_ambiguous_trips_is_collecting_without_preference_history():
    p = mod.build_profile_from_trips(
        [trip(("car", 1000), ("bus", 1000))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14"
    )
    assert p["profile_status"] == "collecting"
    assert p["valid_trip_count"] == 0
    assert p["invalid_trip_reasons"]["primary_mode_tie"] == 1


def test_preference_updates_only_when_a_choice_exists():
    prefs = mod.compute_category_preferences([
        offer("2026-09-01", "habit"),
        offer("2026-09-08", None),
    ])
    assert prefs["habit"]["alpha"] == 2.0
    assert prefs["habit"]["beta"] == 1.0
    assert prefs["habit"]["selected_count"] == 1
    assert prefs["habit"]["observations"] == 1
    assert prefs["challenge"]["alpha"] == 1.0
    assert prefs["challenge"]["beta"] == 2.0
    assert prefs["challenge"]["observations"] == 1


def test_repeated_choices_raise_preference_without_using_completion():
    prefs = mod.compute_category_preferences([
        offer("2026-09-01", "explore"),
        offer("2026-09-08", "explore"),
        offer("2026-09-15", "habit"),
    ])
    assert prefs["explore"]["posterior_mean"] > prefs["habit"]["posterior_mean"]
    assert prefs["explore"]["selected_count"] == 2


def test_family_capability_uses_completion_for_difficulty_not_preference():
    state = mod.compute_family_capability([
        {"week_start": "2026-09-01", "mission_family": "car_to_transit", "target_count": 1, "achievement_rate": 1.0},
        {"week_start": "2026-09-08", "mission_family": "car_to_transit", "target_count": 2, "achievement_rate": .5},
        {"week_start": "2026-09-08", "mission_family": "short_car_to_active", "target_count": 1, "achievement_rate": 1.0},
    ])
    assert state["car_to_transit"]["assignment_count"] == 2
    assert state["car_to_transit"]["completed_count"] == 1
    assert state["car_to_transit"]["last_target_count"] == 2
    assert state["car_to_transit"]["last_achievement_rate"] == .5
    assert state["short_car_to_active"]["max_completed_target_count"] == 1


def test_no_trips_but_choice_history_is_preference_only_not_collecting():
    p = mod.build_profile_from_trips(
        [], user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14",
        offer_history=[offer("2026-09-01", "challenge")],
    )
    assert p["profile_status"] == "preference_only"
    assert p["valid_trip_count"] == 0
    assert p["category_preferences"]["challenge"]["posterior_mean"] > .5


def test_profile_combines_behavior_preference_and_capability():
    p = mod.build_profile_from_trips(
        [trip(("car", 1500)), trip(("bus", 3000))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14",
        offer_history=[offer("2026-09-01", "habit")],
        assignment_history=[
            {"week_start": "2026-09-01", "created_at": "2026-09-01T00:00:00Z", "mission_family": "transit_habit", "target_count": 1, "achievement_rate": 1.0, "completed": True}
        ],
    )
    assert p["profile_status"] == "ready"
    assert p["car_ratio"] == .5
    assert p["category_preferences"]["habit"]["selected_count"] == 1
    assert p["family_capability"]["transit_habit"]["last_target_count"] == 1
    assert p["previous_mission_family"] == "transit_habit"


def test_campaign_timezone_week_bounds_are_converted_to_utc():
    start, end = mod._utc_week_bounds("2026-09-07", "2026-09-14", "Asia/Seoul")
    assert start.startswith("2026-09-06T15:00:00+00:00")
    assert end.startswith("2026-09-13T15:00:00+00:00")

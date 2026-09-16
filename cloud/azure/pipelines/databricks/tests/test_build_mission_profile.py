import build_mission_profile as mod


def trip(*segments):
    return {"segments": [{"model_prediction": mode, "distance_m": distance} for mode, distance in segments]}


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


def test_only_ambiguous_trips_is_collecting():
    p = mod.build_profile_from_trips(
        [trip(("car", 1000), ("bus", 1000))],
        user_id="u1", campaign_id="c1",
        source_week_start="2026-09-07", source_week_end="2026-09-14"
    )
    assert p["profile_status"] == "collecting"
    assert p["valid_trip_count"] == 0
    assert p["invalid_trip_reasons"]["primary_mode_tie"] == 1


def test_campaign_timezone_week_bounds_are_converted_to_utc():
    start, end = mod._utc_week_bounds("2026-09-07", "2026-09-14", "Asia/Seoul")
    assert start.startswith("2026-09-06T15:00:00+00:00")
    assert end.startswith("2026-09-13T15:00:00+00:00")

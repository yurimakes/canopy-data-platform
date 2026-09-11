import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from canopy_api.carbon import CarbonFactorSet, CarbonFactorError, calculate_routes_carbon
from canopy_api.ranking import RecommendationPolicy, recommend_low_carbon_route
from canopy_api.transit.tmap_adapter import normalize_tmap_response


FIXTURE = ROOT / "data" / "fixtures" / "transit" / "tmap_public_transit_20260912_trimmed.json"
FACTORS = ROOT / "data" / "reference" / "carbon_factors.demo.json"


def test_actual_tmap_fixture_normalizes_to_two_routes():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    routes = normalize_tmap_response(payload)
    assert len(routes) == 2
    assert routes[0].total_time_s == 4263
    assert [x.mode for x in routes[0].legs] == ["WALK", "BUS", "WALK", "SUBWAY", "WALK"]
    assert routes[0].legs[1].distance_m == 6148
    assert routes[0].legs[3].distance_m == 22016


def test_unapproved_demo_factors_are_blocked_by_default():
    try:
        CarbonFactorSet.from_json(FACTORS)
    except CarbonFactorError:
        pass
    else:
        raise AssertionError("unapproved factor set must be rejected without explicit opt-in")


def test_carbon_and_practical_low_carbon_recommendation():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    routes = normalize_tmap_response(payload)
    factors = CarbonFactorSet.from_json(FACTORS, allow_unapproved=True)
    calculate_routes_carbon(routes, factors)

    result = recommend_low_carbon_route(
        routes,
        RecommendationPolicy(max_time_over_fastest_pct=20, max_extra_transfers=1),
    )

    # Captured real TMAP sample: route 0 is 8 seconds faster; route 1 has
    # much lower demo carbon and zero transfers.
    assert result["fastest_route_index"] == 0
    assert result["lowest_carbon_route_index"] == 1
    assert result["recommended_route_index"] == 1
    route1 = next(x for x in result["routes"] if x["provider_route_index"] == 1)
    assert abs(route1["carbon_g"] - 51.208) < 0.01


def test_error_fixture_is_valid_negative_fixture():
    path = ROOT / "data" / "fixtures" / "transit" / "odsay_api_key_auth_failed.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["error"][0]["message"].startswith("[ApiKeyAuthFailed]")

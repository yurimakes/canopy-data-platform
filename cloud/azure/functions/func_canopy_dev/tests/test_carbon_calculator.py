from copy import deepcopy
from pathlib import Path

import pytest

from carbon_calculator import (
    CarbonCalculationError,
    calculate_trip_carbon,
    load_policy,
)

POLICY = load_policy(Path(__file__).resolve().parents[1] / "carbon_policy.yaml")


def test_walk_zero():
    result = calculate_trip_carbon(
        [{"segment_id": "walk-1", "predicted_mode": "walk", "distance_m": 1200}],
        POLICY,
    )
    assert result.emission_kgco2e == 0.0


def test_human_bike_zero():
    result = calculate_trip_carbon(
        [{"segment_id": "bike-1", "predicted_mode": "bike", "distance_m": 5000}],
        POLICY,
    )
    assert result.emission_kgco2e == 0.0


def test_bus_3km():
    result = calculate_trip_carbon(
        [{"segment_id": "bus-1", "predicted_mode": "bus", "distance_m": 3000}],
        POLICY,
    )
    assert result.emission_kgco2e == 0.37656


def test_car_3km():
    result = calculate_trip_carbon(
        [{"segment_id": "car-1", "predicted_mode": "car", "distance_m": 3000}],
        POLICY,
    )
    assert result.emission_kgco2e == 0.49773


def test_rail_10km():
    result = calculate_trip_carbon(
        [{"segment_id": "rail-1", "predicted_mode": "rail", "distance_m": 10000}],
        POLICY,
    )
    assert result.emission_kgco2e == 0.1549


def test_multi_segment_trip():
    result = calculate_trip_carbon(
        [
            {"segment_id": "seg-1", "predicted_mode": "walk", "distance_m": 400},
            {"segment_id": "seg-2", "predicted_mode": "bus", "distance_m": 5000},
            {"segment_id": "seg-3", "predicted_mode": "walk", "distance_m": 300},
        ],
        POLICY,
    )
    assert result.distance_km == 5.7
    assert result.emission_kgco2e == 0.6276


def test_user_confirmation_is_ignored_until_policy_is_agreed():
    result = calculate_trip_carbon(
        [{
            "segment_id": "seg-2",
            "predicted_mode": "bus",
            "user_confirmed_mode": "car",
            "distance_m": 3000,
        }],
        POLICY,
    )
    assert result.emission_kgco2e == 0.37656
    assert result.segments[0].predicted_mode == "bus"


def test_missing_distance_is_error_not_zero():
    with pytest.raises(CarbonCalculationError) as exc:
        calculate_trip_carbon(
            [{"segment_id": "seg-1", "predicted_mode": "bus"}],
            POLICY,
        )
    assert exc.value.code == "missing_distance"


def test_missing_factor_is_error_not_zero():
    policy = deepcopy(POLICY)
    policy["factors"]["bus"]["value"] = None

    with pytest.raises(CarbonCalculationError) as exc:
        calculate_trip_carbon(
            [{"segment_id": "seg-1", "predicted_mode": "bus", "distance_m": 1000}],
            policy,
        )
    assert exc.value.code == "missing_factor"


def test_motorcycle_is_explicitly_unsupported():
    with pytest.raises(CarbonCalculationError) as exc:
        calculate_trip_carbon(
            [{"segment_id": "seg-1", "predicted_mode": "motorcycle", "distance_m": 1000}],
            POLICY,
        )
    assert exc.value.code == "unsupported_mode"

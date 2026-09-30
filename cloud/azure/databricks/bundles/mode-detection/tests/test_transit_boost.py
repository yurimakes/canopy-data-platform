import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "reference-model"))

from src.transit_context.resolver import resolve_mode
from src.transit_context.settings import load_settings


def test_applicable_bus_evidence_gets_configured_boost():
    settings = load_settings()
    result = resolve_mode(
        {"walk": 0.55, "bus": 0.40, "rail": 0.05},
        context={"bus_context_score": 0.65, "bus_applicability": "APPLICABLE", "rail_applicability": "NOT_APPLICABLE"},
        settings=settings,
    )
    assert result["final_mode"] == "bus"
    assert result["bus_context_score"] == 0.65


def test_boost_does_not_promote_marginal_rail_or_missing_reference():
    settings = load_settings()
    probabilities = {"walk": 0.55, "bus": 0.05, "rail": 0.40}
    for applicability in ("APPLICABLE", "NOT_APPLICABLE"):
        result = resolve_mode(probabilities, context={"subway_context_score": 0.65, "rail_applicability": applicability}, settings=settings)
        assert result["final_mode"] == "walk"


def test_unrelated_transit_evidence_does_not_inflate_walk_confidence():
    result = resolve_mode(
        {"walk": 0.75, "bus": 0.20, "rail": 0.05},
        context={"bus_context_score": 0.60, "bus_applicability": "APPLICABLE"},
        settings=load_settings(),
    )
    assert result["final_mode"] == "walk"
    assert result["decision_confidence"] == 0.75


def test_strong_applicable_subway_evidence_reinforces_rail_but_caps_confidence():
    result = resolve_mode(
        {"walk": 0.55, "rail": 0.40, "bus": 0.05},
        context={
            "subway_context_score": 0.90,
            "rail_applicability": "APPLICABLE",
            "subway_observed_station_count": 2,
            "subway_line_score": 1.0,
            "subway_sequence_score": 0.5,
        },
        settings=load_settings(),
    )
    assert result["final_mode"] == "rail"
    assert result["subway_context_score"] == 0.90
    assert result["decision_confidence"] == 1.0


def test_out_of_range_context_never_emits_confidence_above_one():
    result = resolve_mode(
        {"bus": 0.6, "walk": 0.4},
        context={"bus_context_score": 1.5, "bus_applicability": "NOT_APPLICABLE"},
        settings=load_settings(),
    )
    assert result["bus_context_score"] == 1.0
    assert result["decision_confidence"] <= 1.0

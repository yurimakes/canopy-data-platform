"""Shared adapter to the unchanged team carbon module for final and legacy results."""
from decimal import Decimal
from functools import lru_cache
import importlib.util
from pathlib import Path
import sys
from .trip_processor import MODES


@lru_cache
def calculator():
    # Deployment packages the team's module at root; local runs reference its source.
    path = Path(__file__).resolve().parents[1] / "carbon_calculator.py"
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "cloud/azure/functions/func_canopy_dev/carbon_calculator.py"
    spec = importlib.util.spec_from_file_location("canopy_team_carbon", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, module.load_policy(path.with_name("carbon_policy.yaml"))


def carbon_for(segments, mode_field):
    module, policy = calculator()
    # The legacy calculator accepts predicted_mode. Map an ephemeral input only;
    # never modify the saved model prediction or the team's predicted-only endpoint.
    inputs = [{"segment_id": s["segment_id"], "predicted_mode": s[mode_field],
               "distance_m": s["distance_m"]} for s in segments]
    result = module.calculate_trip_carbon(inputs, policy)
    return result


def finalize_result(trip, segments, completed_at):
    """Calculate once from system FinalSegments, before ready. No user feedback."""
    carbon = carbon_for(segments, "mode")
    for segment, value in zip(segments, carbon.segments):
        segment["carbon_kg"] = value.emission_kgco2e_raw
    distances = {mode: sum((Decimal(str(s["distance_m"])) for s in segments if s["mode"] == mode), Decimal(0))
                 for mode in MODES}
    summary = {"schema_version": "canopy.confirmed-trip.v1", "trip_id": trip["trip_id"], "user_id": trip["user_id"],
               "campaign_id": trip["campaign_id"], "started_at": trip["started_at"], "ended_at": trip["ended_at"],
               "confirmed_at": completed_at, "revision": 1, "confirmation_status": "confirmed",
               "confirmation_source": "system", "total_distance_m": float(sum(distances.values())),
               "total_carbon_kg": carbon.emission_kgco2e,
               **{mode + "_distance_m": float(value) for mode, value in distances.items()},
               "carbon_unit": "kgCO2e", "carbon_policy_version": carbon.policy_version,
               "factor_version": carbon.factor_version, "mode_source": "model_prediction",
               "model_version": trip["model_version"], "is_mock": trip["is_mock"]}
    trip.update(confirmed_trip=summary, revision=1, confirmed_at=completed_at,
                confirmation_status="confirmed", confirmation_source="system",
                carbon={"kg_co2e": carbon.emission_kgco2e, "recalculated_kg_co2e": None,
                        "mode_source": "model_prediction", "user_confirmation_applied": False,
                        "policy_version": carbon.policy_version, "factor_version": carbon.factor_version, "unit": "kgCO2e"})



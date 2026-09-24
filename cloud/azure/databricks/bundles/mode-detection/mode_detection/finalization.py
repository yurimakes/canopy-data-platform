"""Build the final durable trip payload at the stateful pipeline boundary."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

from .distance import DistanceState
from .lifecycle import SealedModeDetection


def _iso(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@lru_cache(maxsize=4)
def load_carbon_policy(path: str) -> dict:
    policy = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    required = {
        "policy_version",
        "factor_version",
        "supported_modes",
        "distance",
        "output",
        "factors",
    }
    missing = required - set(policy)
    if missing:
        raise ValueError(f"carbon policy missing keys: {sorted(missing)}")
    return policy


def build_complete_payload(
    sealed: SealedModeDetection,
    distances: DistanceState,
    *,
    model_name: str,
    model_version: str,
    feature_version: str,
    sealed_at,
    carbon_policy_path: str,
) -> dict:
    event = sealed.trip_end
    policy = load_carbon_policy(carbon_policy_path)
    supported = set(policy["supported_modes"])
    factors = policy["factors"]
    meters_per_km = float(policy["distance"]["meters_per_km"])
    decimals = int(policy["output"]["storage_decimals"])
    distance_values = distances.distances_for(sealed.segments)

    segments = []
    total_distance = 0.0
    total_carbon = 0.0
    for index, (segment, distance_m) in enumerate(
        zip(sealed.segments, distance_values), start=1
    ):
        mode = segment.mode
        if mode not in supported:
            raise ValueError(f"unsupported carbon mode: {mode}")
        carbon_kg = (distance_m / meters_per_km) * float(factors[mode]["value"])
        total_distance += distance_m
        total_carbon += carbon_kg
        segments.append(
            {
                "segment_id": f"{event.trip_id}:segment:{index}",
                "mode": mode,
                "model_prediction": mode,
                "start_time": _iso(segment.start_time),
                "end_time": _iso(segment.end_time),
                "distance_m": round(distance_m, 6),
                "confidence": segment.confidence,
                "prediction_count": segment.prediction_count,
                "carbon_kg": carbon_kg,
            }
        )

    sealed_at_iso = _iso(sealed_at)
    payload = {
        "id": event.trip_id,
        "type": "trip",
        "trip_id": event.trip_id,
        "user_id": event.user_id,
        "campaign_id": event.campaign_id,
        "status": "ready",
        "mode_detection_status": sealed.status,
        "mode_detection_reason": sealed.reason,
        "started_at": _iso(event.started_at),
        "ended_at": _iso(event.ended_at),
        "updated_at": sealed_at_iso,
        "processing_generation": event.processing_generation,
        "expected_last_sequence": event.expected_last_sequence,
        "segments": segments,
        "model_name": model_name,
        "model_version": model_version,
        "feature_version": feature_version,
        "total_distance_m": round(total_distance, 6),
        "carbon": {
            "kg_co2e": round(total_carbon, decimals),
            "policy_version": str(policy["policy_version"]),
            "factor_version": str(policy["factor_version"]),
            "unit": str(policy["output"]["emission_unit"]),
            "mode_source": "model_prediction" if segments else "unavailable",
            "user_confirmation_applied": False,
        },
        "sealed_at": sealed_at_iso,
    }
    semantic = dict(payload)
    semantic.pop("updated_at")
    semantic.pop("sealed_at")
    payload["finalization_hash"] = hashlib.sha256(
        canonical(semantic).encode("utf-8")
    ).hexdigest()
    payload["document_json"] = canonical(payload)
    return payload

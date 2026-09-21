"""Atomic confirmation of FinalSegments; independent of the inference provider."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json

from .cosmos_service import Conflict
from .trip_carbon import carbon_for
from .trip_processor import MODES, validate_result
from .trip_service import ApiError, iso, required


def validate_confirmation(trip, original_segments):
    # Future commute eligibility checks belong here, before any confirmation write.
    validate_result(trip, {"trip_id": trip["trip_id"], "model_version": trip["model_version"],
                           "segments": original_segments})


def confirm(service, trip_id, user_id, body):
    request_id = required(body, "request_id")
    revision = body.get("expected_revision")
    if type(revision) is not int or revision < 0:
        raise ApiError(400, "invalid_field", "expected_revision must be a nonnegative integer")
    entries = body.get("segments")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
        raise ApiError(400, "invalid_segments", "send all segments (1 to 1000)")
    modes = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"segment_id", "confirmed_mode"}:
            raise ApiError(400, "invalid_segments", "only segment_id and confirmed_mode are accepted")
        sid = required(entry, "segment_id")
        if not isinstance(entry["confirmed_mode"], str) or entry["confirmed_mode"] not in MODES or sid in modes:
            raise ApiError(400, "invalid_segments", "invalid mode or duplicate segment_id")
        modes[sid] = entry["confirmed_mode"]
    fingerprint = hashlib.sha256(json.dumps([revision, modes], sort_keys=True).encode()).hexdigest()
    for _ in range(8):
        trip = service.get(trip_id, user_id)
        history = trip.get("confirmation_history", [])
        previous = next((h for h in history if h["request_id"] == request_id), None)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ApiError(409, "idempotency_conflict", "request_id was used with different confirmation values")
            return trip  # Never roll back a later revision when an old retry arrives.
        if trip["status"] != "ready":
            raise ApiError(409, "trip_not_ready", "wait for the Trip result")
        if trip.get("revision", 0) != revision:
            raise ApiError(409, "revision_conflict", "reload the latest Trip before editing")
        if len(history) >= 100:
            raise ApiError(409, "revision_limit", "maximum 100 confirmations per Trip")
        original = deepcopy(trip.get("original_segments", trip["segments"]))
        if set(modes) != {s["segment_id"] for s in original}:
            raise ApiError(400, "invalid_segments", "segment IDs must match the complete Trip")
        validate_confirmation(trip, original)
        now = iso(service.clock())
        confirmed = [{**s, "mode": modes[s["segment_id"]], "confirmed_mode": modes[s["segment_id"]],
                      "corrected": modes[s["segment_id"]] != s["mode"],
                      "correction_status": "pending_review" if modes[s["segment_id"]] != s["mode"] else "none",
                      "confirmation_time": now, "last_request_id": request_id} for s in original]
        prediction = carbon_for(original, "mode")
        corrected = carbon_for(confirmed, "confirmed_mode")
        for segment, carbon in zip(confirmed, corrected.segments):
            segment["carbon_kg"] = carbon.emission_kgco2e_raw
        distances = {mode: sum((Decimal(str(s["distance_m"])) for s in confirmed
                               if s["confirmed_mode"] == mode), Decimal(0)) for mode in MODES}
        summary = {"schema_version": "canopy.confirmed-trip.v1", "trip_id": trip_id, "user_id": user_id,
                   "campaign_id": trip["campaign_id"], "started_at": trip["started_at"], "ended_at": trip["ended_at"],
                   "confirmed_at": now, "revision": revision + 1, "confirmation_status": "confirmed",
                   "total_distance_m": float(sum(distances.values())), "total_carbon_kg": corrected.emission_kgco2e,
                   **{mode + "_distance_m": float(distance) for mode, distance in distances.items()},
                   "carbon_unit": "kgCO2e", "carbon_policy_version": corrected.policy_version,
                   "factor_version": corrected.factor_version, "mode_source": "confirmed_mode",
                   "is_mock": trip["is_mock"], "model_version": trip["model_version"]}
        trip.update(original_segments=original, confirmed_segments=confirmed, segments=confirmed,
                    revision=revision + 1, confirmed_at=now, updated_at=now, confirmation_status="confirmed",
                    confirmed_trip=summary,
                    carbon={"kg_co2e": prediction.emission_kgco2e,
                            "recalculated_kg_co2e": corrected.emission_kgco2e, "mode_source": "confirmed_mode",
                            "user_confirmation_applied": True, "policy_version": corrected.policy_version,
                            "factor_version": corrected.factor_version, "unit": "kgCO2e"},
                    confirmation_history=history + [{"request_id": request_id, "fingerprint": fingerprint,
                        "revision": revision + 1, "confirmed_at": now, "modes": modes,
                        "total_carbon_kg": corrected.emission_kgco2e}])
        if len(json.dumps(trip).encode()) > 1800000:
            raise ApiError(409, "revision_limit", "confirmation history has reached the document limit")
        try:
            saved = service.store.replace(trip)
            from .trip_service import LOG
            LOG.info("trip_confirmed trip_id=%s revision=%s", trip_id, revision + 1)
            return saved
        except Conflict:
            continue
    raise ApiError(409, "concurrent_update", "retry the same confirmation request")

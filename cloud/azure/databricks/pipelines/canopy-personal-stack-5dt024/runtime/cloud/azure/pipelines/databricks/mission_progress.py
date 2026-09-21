"""Mission v3.2 progress calculation core.

This module intentionally contains no ADLS, Cosmos, Databricks Job, or Lakeflow
wiring. Integration owners can call ``build_progress_rows`` (Python records) or
adapt the same functions inside their Spark task.

Contract highlights:
- consume the *issued* assignment ``completion_rule`` snapshot, never the
  current mission policy file;
- use only canonical ``status=ready`` Trips;
- de-duplicate by ``trip_id`` using the latest Trip version before evaluation;
- use the same strict primary-mode rule as Weekly Gold: every segment must have
  a supported mode and positive finite distance, and the summed-distance winner
  must be unique;
- recompute progress idempotently from the canonical Trip set rather than
  incrementing an existing counter;
- one Trip may progress multiple assignments, but only once per assignment.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

PROGRESS_VERSION = "mission-progress-v1"
SUPPORTED_MODES = ("walk", "bike", "car", "bus", "rail")
SUPPORTED_METRICS = ("qualifying_trip_count", "distinct_day_count", "distinct_mode_count")


class MissionProgressError(ValueError):
    """Raised when the issued bundle or completion-rule contract is invalid."""


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value: Any, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise MissionProgressError(f"{field_name} must be YYYY-MM-DD") from exc
    raise MissionProgressError(f"{field_name} must be YYYY-MM-DD")


def _week_bounds(bundle: Mapping[str, Any], campaign_timezone: str) -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(campaign_timezone)
    except Exception as exc:  # pragma: no cover - platform timezone database failure
        raise MissionProgressError(f"invalid campaign_timezone: {campaign_timezone}") from exc
    start_date = _parse_date(bundle.get("week_start"), "week_start")
    end_date = _parse_date(bundle.get("week_end"), "week_end")
    if end_date <= start_date:
        raise MissionProgressError("week_end must be after week_start")
    start_local = datetime.combine(start_date, time.min, tzinfo=tz)
    end_local = datetime.combine(end_date, time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def derive_trip_primary_mode(trip: Mapping[str, Any]) -> tuple[str | None, float | None, str | None]:
    """Return ``(primary_mode, total_distance_m, invalid_reason)``.

    Any invalid segment invalidates the Trip's primary-mode fact. A distance tie
    is also invalid instead of being broken arbitrarily.
    """
    segments = trip.get("segments")
    if not isinstance(segments, list) or not segments:
        return None, None, "invalid_segment"

    distance_by_mode: dict[str, float] = defaultdict(float)
    total_distance_m = 0.0
    for segment in segments:
        if not isinstance(segment, Mapping):
            return None, None, "invalid_segment"
        raw_mode = segment.get("model_prediction")
        mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else None
        distance_m = _as_number(segment.get("distance_m"))
        if mode not in SUPPORTED_MODES or distance_m is None or distance_m <= 0:
            return None, None, "invalid_segment"
        distance_by_mode[mode] += distance_m
        total_distance_m += distance_m

    max_distance = max(distance_by_mode.values())
    winners = [mode for mode, value in distance_by_mode.items() if abs(value - max_distance) < 1e-9]
    if len(winners) != 1:
        return None, total_distance_m, "primary_mode_tie"
    return winners[0], total_distance_m, None


def _trip_version_key(trip: Mapping[str, Any]) -> tuple[datetime, int, str]:
    updated = _parse_datetime(trip.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)
    generation = trip.get("processing_generation")
    generation_value = int(generation) if isinstance(generation, int) and not isinstance(generation, bool) else -1
    finalization_hash = trip.get("finalization_hash")
    return updated, generation_value, finalization_hash if isinstance(finalization_hash, str) else ""


def latest_ready_trips(
    trips: Iterable[Mapping[str, Any]],
    *,
    campaign_id: str,
    user_id: str,
) -> list[Mapping[str, Any]]:
    """Choose the latest version per Trip, then keep only canonical ready Trips.

    Choosing the latest version *before* the ready/status check means a corrected
    or invalidated newer version replaces the older contribution instead of
    double-counting or retaining stale progress.
    """
    latest: dict[str, Mapping[str, Any]] = {}
    for trip in trips:
        if trip.get("campaign_id") != campaign_id or trip.get("user_id") != user_id:
            continue
        trip_id = trip.get("trip_id")
        if not isinstance(trip_id, str) or not trip_id:
            continue
        previous = latest.get(trip_id)
        if previous is None or _trip_version_key(trip) > _trip_version_key(previous):
            latest[trip_id] = trip
    return [trip for trip in latest.values() if trip.get("status") == "ready" and not trip.get("is_mock") and not (trip.get("confirmed_trip") or {}).get("is_mock") and (trip.get('data_quality') or {}).get('status')!='partial']


def _validate_assignment(bundle: Mapping[str, Any], assignment: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    rule = assignment.get("completion_rule")
    if not isinstance(rule, Mapping):
        raise MissionProgressError("issued assignment must contain completion_rule snapshot")
    rule = dict(rule)
    metric = rule.get("metric")
    if metric not in SUPPORTED_METRICS:
        raise MissionProgressError(f"unsupported completion_rule.metric: {metric}")
    target = rule.get("target_count", assignment.get("target_count"))
    if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
        raise MissionProgressError("completion_rule.target_count must be a positive integer")
    if assignment.get("target_count") not in (None, target):
        raise MissionProgressError("assignment target_count and completion_rule target_count disagree")
    if rule.get("source") not in (None, "canonical_ready_trip"):
        raise MissionProgressError("completion_rule.source must be canonical_ready_trip")
    if rule.get("dedupe_key") not in (None, "trip_id"):
        raise MissionProgressError("completion_rule.dedupe_key must be trip_id")
    if rule.get("time_window") not in (None, "assignment_week"):
        raise MissionProgressError("completion_rule.time_window must be assignment_week")
    accepted = rule.get("accepted_primary_modes")
    if not isinstance(accepted, list) or not accepted:
        raise MissionProgressError("completion_rule.accepted_primary_modes is required")
    normalized = []
    for mode in accepted:
        if not isinstance(mode, str) or mode.lower() not in SUPPORTED_MODES:
            raise MissionProgressError(f"unsupported accepted_primary_mode: {mode}")
        normalized.append(mode.lower())
    rule["accepted_primary_modes"] = normalized
    return rule, target


def _qualifying_events(
    *,
    bundle: Mapping[str, Any],
    assignment: Mapping[str, Any],
    trips: Iterable[Mapping[str, Any]],
    campaign_timezone: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rule, _ = _validate_assignment(bundle, assignment)
    week_start_utc, week_end_utc = _week_bounds(bundle, campaign_timezone)
    tz = ZoneInfo(campaign_timezone)
    accepted_modes = set(rule["accepted_primary_modes"])
    min_km = _as_number(rule.get("min_trip_distance_km"))
    max_km = _as_number(rule.get("max_trip_distance_km"))
    if min_km is not None and min_km < 0:
        raise MissionProgressError("min_trip_distance_km cannot be negative")
    if max_km is not None and max_km < 0:
        raise MissionProgressError("max_trip_distance_km cannot be negative")
    if min_km is not None and max_km is not None and max_km < min_km:
        raise MissionProgressError("max_trip_distance_km cannot be below min_trip_distance_km")

    invalid_reasons: dict[str, int] = defaultdict(int)
    events: list[dict[str, Any]] = []
    for trip in latest_ready_trips(
        trips,
        campaign_id=str(bundle.get("campaign_id")),
        user_id=str(bundle.get("user_id")),
    ):
        ended_at = _parse_datetime(trip.get("ended_at"))
        if ended_at is None:
            invalid_reasons["invalid_ended_at"] += 1
            continue
        started_at = _parse_datetime(trip.get("started_at")) or ended_at
        if not (week_start_utc <= started_at < week_end_utc):
            continue
        primary_mode, total_distance_m, invalid_reason = derive_trip_primary_mode(trip)
        if invalid_reason:
            invalid_reasons[invalid_reason] += 1
            continue
        assert primary_mode is not None and total_distance_m is not None
        if primary_mode not in accepted_modes:
            continue
        distance_km = total_distance_m / 1000.0
        if min_km is not None and distance_km < min_km:
            continue
        if max_km is not None and distance_km > max_km:
            continue
        events.append({
            "trip_id": trip["trip_id"],
            "ended_at": ended_at,
            "local_date": started_at.astimezone(tz).date().isoformat(),
            "primary_mode": primary_mode,
            "distance_m": total_distance_m,
        })
    events.sort(key=lambda event: (event["ended_at"], event["trip_id"]))
    return events, dict(invalid_reasons)


def _metric_progress(metric: str, events: list[dict[str, Any]], target: int) -> tuple[int, datetime | None]:
    completed_at: datetime | None = None
    if metric == "qualifying_trip_count":
        progress_count = len(events)
        if progress_count >= target:
            completed_at = events[target - 1]["ended_at"]
        return progress_count, completed_at

    if metric == "distinct_day_count":
        seen: set[str] = set()
        for event in events:
            seen.add(event["local_date"])
            if len(seen) >= target and completed_at is None:
                completed_at = event["ended_at"]
        return len(seen), completed_at

    if metric == "distinct_mode_count":
        seen_modes: set[str] = set()
        for event in events:
            seen_modes.add(event["primary_mode"])
            if len(seen_modes) >= target and completed_at is None:
                completed_at = event["ended_at"]
        return len(seen_modes), completed_at

    raise MissionProgressError(f"unsupported metric: {metric}")


def evaluate_assignment_progress(
    *,
    bundle: Mapping[str, Any],
    assignment: Mapping[str, Any],
    trips: Iterable[Mapping[str, Any]],
    campaign_timezone: str,
    as_of_iso: str,
) -> dict[str, Any]:
    """Recompute one assignment from canonical Trips and its frozen rule."""
    rule, target = _validate_assignment(bundle, assignment)
    as_of = _parse_datetime(as_of_iso)
    if as_of is None:
        raise MissionProgressError("as_of_iso must be a valid ISO-8601 timestamp")
    _, week_end_utc = _week_bounds(bundle, campaign_timezone)
    events, invalid_reasons = _qualifying_events(
        bundle=bundle,
        assignment=assignment,
        trips=trips,
        campaign_timezone=campaign_timezone,
    )
    progress_count, completed_at = _metric_progress(str(rule["metric"]), events, target)
    completed = progress_count >= target
    achievement_rate = min(progress_count / target, 1.0)
    status = "completed" if completed else ("expired" if as_of >= week_end_utc else "active")

    return {
        "campaign_id": bundle.get("campaign_id"),
        "user_id": bundle.get("user_id"),
        "bundle_id": bundle.get("bundle_id"),
        "assignment_id": assignment.get("assignment_id"),
        "mission_template_id": assignment.get("mission_template_id"),
        "mission_family": assignment.get("mission_family"),
        "category_id": assignment.get("category_id"),
        "week_start": bundle.get("week_start"),
        "week_end": bundle.get("week_end"),
        "target_count": target,
        "progress_count": progress_count,
        "achievement_rate": achievement_rate,
        "completed": completed,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "status": status,
        "qualified_trip_ids": [event["trip_id"] for event in events],
        "qualified_primary_modes": sorted({event["primary_mode"] for event in events}),
        "qualified_local_dates": sorted({event["local_date"] for event in events}),
        "completion_metric": rule["metric"],
        "primary_mode_invalid_reasons": invalid_reasons,
        "progress_version": PROGRESS_VERSION,
        "updated_at": as_of.isoformat(),
    }


def evaluate_bundle_progress(
    *,
    bundle: Mapping[str, Any],
    trips: Iterable[Mapping[str, Any]],
    campaign_timezone: str,
    as_of_iso: str,
) -> list[dict[str, Any]]:
    missions = bundle.get("missions")
    if not isinstance(missions, list) or not missions:
        raise MissionProgressError("mission bundle must contain missions")
    trip_rows = list(trips)
    return [
        evaluate_assignment_progress(
            bundle=bundle,
            assignment=assignment,
            trips=trip_rows,
            campaign_timezone=campaign_timezone,
            as_of_iso=as_of_iso,
        )
        for assignment in missions
    ]


def build_progress_rows(
    bundle_rows: Iterable[Mapping[str, Any]],
    trip_rows: Iterable[Mapping[str, Any]],
    *,
    campaign_timezone: str,
    as_of_iso: str,
) -> list[dict[str, Any]]:
    """Batch-friendly adapter for integration tests and Databricks task wiring.

    The integration owner may partition Spark data by campaign/user/week and call
    the lower-level evaluator, or translate the same contract to native Spark
    expressions. This function deliberately performs no storage I/O.
    """
    trips = list(trip_rows)
    output: list[dict[str, Any]] = []
    for bundle in bundle_rows:
        output.extend(
            evaluate_bundle_progress(
                bundle=bundle,
                trips=trips,
                campaign_timezone=campaign_timezone,
                as_of_iso=as_of_iso,
            )
        )
    return output

"""Mission v3.2 weekly Mission Response builder.

This module intentionally contains no ADLS, Cosmos, Lakeflow, or ADF wiring.
It converts issued Mission Bundle snapshots + final Mission Progress rows +
optional UI events into one analytical row per issued assignment.

Rules:
- preserve every issued assignment, including incomplete assignments;
- copy category/family/target/comparability from the frozen Bundle snapshot;
- copy progress/completion from Mission Progress, never from UI button events;
- UI events are optional descriptive signals only (shown / started);
- de-duplicate UI events by event_id;
- produce deterministic rows suitable for ADLS Gold mission_response_weekly.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

RESPONSE_VERSION = "mission-response-v1"


class MissionResponseError(ValueError):
    """Raised when Mission Bundle / Progress input violates the v3.2 contract."""


def _assignment_index(
    bundle_rows: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for bundle in bundle_rows:
        missions = bundle.get("missions")
        if not isinstance(missions, list) or not missions:
            raise MissionResponseError("mission bundle must contain missions")
        for assignment in missions:
            assignment_id = assignment.get("assignment_id")
            if not isinstance(assignment_id, str) or not assignment_id:
                raise MissionResponseError("assignment_id is required")
            if assignment_id in index:
                raise MissionResponseError(f"duplicate assignment_id: {assignment_id}")
            index[assignment_id] = (bundle, assignment)
    return index


def _progress_index(progress_rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for row in progress_rows:
        assignment_id = row.get("assignment_id")
        if not isinstance(assignment_id, str) or not assignment_id:
            raise MissionResponseError("progress assignment_id is required")
        if assignment_id in index:
            raise MissionResponseError(f"duplicate progress assignment_id: {assignment_id}")
        index[assignment_id] = row
    return index


def _event_counts(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    seen_event_ids: set[str] = set()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"shown": 0, "started": 0})
    for event in events:
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id:
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
        assignment_id = event.get("assignment_id")
        if not isinstance(assignment_id, str) or not assignment_id:
            continue
        event_type = event.get("event_type")
        if event_type in ("shown", "started"):
            counts[assignment_id][event_type] += 1
    return dict(counts)


def _positive_int(value: Any, field: str, assignment_id: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MissionResponseError(f"invalid {field} for {assignment_id}")
    return value


def build_response_rows(
    bundle_rows: Iterable[Mapping[str, Any]],
    progress_rows: Iterable[Mapping[str, Any]],
    ui_events: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return one Mission Response row per issued assignment.

    Missing Progress is represented as zero progress so an issued-but-unprogressed
    assignment remains visible in analytical history. Unknown Progress rows fail
    closed because they cannot be traced to an issued assignment.
    """
    assignments = _assignment_index(bundle_rows)
    progress = _progress_index(progress_rows)
    events = _event_counts(ui_events)

    unknown_progress = set(progress) - set(assignments)
    if unknown_progress:
        raise MissionResponseError(
            "progress contains assignment_ids not present in issued bundles: "
            + ", ".join(sorted(unknown_progress))
        )

    rows: list[dict[str, Any]] = []
    for assignment_id in sorted(assignments):
        bundle, assignment = assignments[assignment_id]
        p = progress.get(assignment_id, {})
        counts = events.get(assignment_id, {"shown": 0, "started": 0})

        target_count = _positive_int(assignment.get("target_count"), "target_count", assignment_id)
        common_target_count = _positive_int(
            assignment.get("common_target_count", bundle.get("common_target_count")),
            "common_target_count",
            assignment_id,
        )

        affinity_comparable = assignment.get("affinity_comparable")
        difficulty_comparable = assignment.get("difficulty_comparable")
        if not isinstance(affinity_comparable, bool) or not isinstance(difficulty_comparable, bool):
            raise MissionResponseError(f"comparability flags are required for {assignment_id}")

        progress_count = p.get("progress_count", 0)
        achievement_rate = p.get("achievement_rate", 0.0)
        completed = p.get("completed", False)
        if not isinstance(progress_count, int) or isinstance(progress_count, bool) or progress_count < 0:
            raise MissionResponseError(f"invalid progress_count for {assignment_id}")
        if not isinstance(achievement_rate, (int, float)) or isinstance(achievement_rate, bool) or achievement_rate < 0:
            raise MissionResponseError(f"invalid achievement_rate for {assignment_id}")
        if not isinstance(completed, bool):
            raise MissionResponseError(f"invalid completed for {assignment_id}")

        qualified_trip_ids = p.get("qualified_trip_ids", [])
        if qualified_trip_ids is None:
            qualified_trip_ids = []
        if not isinstance(qualified_trip_ids, list):
            raise MissionResponseError(f"qualified_trip_ids must be a list for {assignment_id}")
        linked_trip_count = len({str(x) for x in qualified_trip_ids if x is not None})

        rows.append({
            "campaign_id": bundle.get("campaign_id"),
            "user_id": bundle.get("user_id"),
            "week_start": bundle.get("week_start"),
            "week_end": bundle.get("week_end"),
            "bundle_id": bundle.get("bundle_id"),
            "assignment_id": assignment_id,
            "mission_template_id": assignment.get("mission_template_id"),
            "mission_family": assignment.get("mission_family"),
            "category_id": assignment.get("category_id"),
            "difficulty_band": assignment.get("difficulty_band"),
            "common_target_count": common_target_count,
            "target_count": target_count,
            "affinity_comparable": affinity_comparable,
            "difficulty_comparable": difficulty_comparable,
            "preference_comparable": affinity_comparable,
            "mission_shown_count": counts["shown"],
            "mission_started_count": counts["started"],
            "mission_completed_count": 1 if completed else 0,
            "progress_count": progress_count,
            "achievement_rate": float(achievement_rate),
            "completed": completed,
            "linked_trip_count": linked_trip_count,
            "policy_version": bundle.get("policy_version"),
            "response_version": RESPONSE_VERSION,
        })
    return rows

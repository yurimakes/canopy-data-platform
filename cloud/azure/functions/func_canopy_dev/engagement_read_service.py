"""Pure response projection for reward ledger and ranking snapshot reads.

This module never calculates or writes rewards/ranks. It only converts the Cosmos
serving projections produced from Gold data into the public API contract.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone


class EngagementContractError(ValueError):
    pass


def _encode_cursor(kind: str, offset: int, source_id: str) -> str:
    raw = json.dumps({"v": 1, "kind": kind, "offset": offset, "source_id": source_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, kind: str, source_id: str) -> int:
    if not cursor:
        return 0
    try:
        cursor += "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor).decode("utf-8"))
        if payload != {
            "v": 1,
            "kind": kind,
            "offset": payload.get("offset"),
            "source_id": source_id,
        }:
            raise ValueError
        offset = int(payload["offset"])
        if offset < 0:
            raise ValueError
        return offset
    except Exception as exc:
        raise EngagementContractError("invalid_cursor") from exc


def _page(values: list, page_size: int, cursor: str | None, kind: str, source_id: str):
    offset = _decode_cursor(cursor, kind, source_id)
    selected = values[offset : offset + page_size]
    next_offset = offset + len(selected)
    next_cursor = _encode_cursor(kind, next_offset, source_id) if next_offset < len(values) else None
    return selected, next_cursor


def _timestamp(value) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return value


def build_reward_response(
    records: list[dict],
    *,
    campaign_id: str,
    user_id: str,
    week_start: str,
    week_end: str,
    page_size: int,
    cursor: str | None,
    requested_at: str | None = None,
) -> dict:
    requested_at = requested_at or datetime.now(timezone.utc).isoformat()
    summaries = [r for r in records if r.get("document_type") == "reward_projection"]
    ledger = [
        r for r in records
        if r.get("document_type") != "reward_projection" and r.get("status") in {"paid", "adjustment", "processing"}
    ]
    for record in ledger:
        if record.get("user_id") != user_id or record.get("campaign_id") != campaign_id or record.get("week") != week_start:
            raise EngagementContractError("reward_boundary_mismatch")
        if not isinstance(record.get("points"), (int, float)):
            raise EngagementContractError("invalid_reward_points")

    ledger.sort(key=lambda item: (_timestamp(item.get("created_at")), str(item.get("reward_id") or item.get("id"))), reverse=True)
    source_id = f"{campaign_id}:{user_id}:{week_start}"
    page, next_cursor = _page(ledger, page_size, cursor, "reward", source_id)
    statuses = {record["status"] for record in ledger}
    projection_status = summaries[0].get("projection_status") if summaries else None
    status = (
        "processing" if projection_status == "processing" or "processing" in statuses
        else "settled" if ledger
        else "empty"
    )
    policy_versions = sorted({str(r["policy_version"]) for r in ledger if r.get("policy_version")})
    updated_values = [_timestamp(r.get("created_at")) for r in ledger] + [
        _timestamp(r.get("generated_at")) for r in summaries
    ]
    updated_at = max((value for value in updated_values if value), default=requested_at)
    entries = [{
        "reward_id": str(record.get("reward_id") or record.get("id")),
        "label": str(record.get("reason") or "주간 저탄소 이동 보상"),
        "points": record["points"],
        "status": "adjusted" if record["status"] == "adjustment" else record["status"],
        "occurred_at": _timestamp(record.get("created_at")) or updated_at,
    } for record in page]
    return {
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "status": status,
        "total_points": sum(record["points"] for record in ledger if record["status"] in {"paid", "adjustment"}),
        "updated_at": updated_at,
        "policy_version": policy_versions[0] if len(policy_versions) == 1 else ("mixed" if policy_versions else None),
        "finalized": status != "processing",
        "entries": entries,
        "next_cursor": next_cursor,
    }


def build_ranking_response(
    snapshot: dict | None,
    *,
    campaign_id: str,
    user_id: str,
    scope: str,
    week_start: str,
    week_end: str,
    page_size: int,
    cursor: str | None,
) -> dict:
    if scope not in {"individual", "department"}:
        raise EngagementContractError("invalid_scope")
    if snapshot is None:
        if cursor:
            raise EngagementContractError("invalid_cursor")
        return {
            "scope": scope,
            "campaign_id": campaign_id,
            "week_start": week_start,
            "week_end": week_end,
            "snapshot_status": "in_progress",
            "generated_at": None,
            "policy_version": None,
            "aggregation_version": None,
            "finalized": False,
            "score_unit": "points",
            "entries": [],
            "next_cursor": None,
        }
    if snapshot.get("campaign_id") != campaign_id or snapshot.get("week_start", snapshot.get("week")) != week_start or snapshot.get("scope") != scope:
        raise EngagementContractError("ranking_boundary_mismatch")
    status = snapshot.get("snapshot_status", "finalized")
    if status not in {"finalized", "in_progress"}:
        raise EngagementContractError("invalid_snapshot_status")
    raw_entries = snapshot.get("entries") or []
    if not isinstance(raw_entries, list):
        raise EngagementContractError("invalid_ranking_entries")
    source_id = str(snapshot.get("id") or f"{campaign_id}:{week_start}:{scope}")
    page, next_cursor = _page(raw_entries, page_size, cursor, "ranking", source_id)
    entries = []
    for index, entry in enumerate(page):
        rank = entry.get("rank")
        score = entry.get("score")
        if not isinstance(rank, int) or rank < 1 or not isinstance(score, (int, float)):
            raise EngagementContractError("invalid_ranking_entry")
        members = entry.get("member_user_ids") or []
        is_me = entry.get("user_id") == user_id if scope == "individual" else user_id in members
        entries.append({
            "rank": rank,
            "subject_id": str(entry.get("public_subject_id") or entry.get("subject_id") or f"{scope}-{index + 1}"),
            "display_name": str(entry.get("display_name") or "비공개"),
            "score": score,
            "is_me": is_me,
        })
    return {
        "scope": scope,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": str(snapshot.get("week_end") or week_end),
        "snapshot_status": status,
        "generated_at": snapshot.get("generated_at"),
        "policy_version": snapshot.get("policy_version"),
        "aggregation_version": snapshot.get("aggregation_version"),
        "finalized": status == "finalized",
        "score_unit": "points",
        "entries": entries,
        "next_cursor": next_cursor,
    }

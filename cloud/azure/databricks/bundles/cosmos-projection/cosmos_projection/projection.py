"""Idempotent Cosmos projection of one canonical Gold payload."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_body(value: dict) -> dict:
    return {key: deepcopy(item) for key, item in value.items() if key not in SYSTEM_FIELDS}


def merge_projection(current: dict | None, payload: dict, *, allow_missing_create: bool) -> tuple[str, dict]:
    """Return projection action + body without performing I/O."""
    if payload.get("id") != payload.get("trip_id"):
        raise ValueError("Gold payload id must equal trip_id")
    if not payload.get("user_id"):
        raise ValueError("Gold payload user_id is required")
    if not payload.get("finalization_hash"):
        raise ValueError("Gold payload finalization_hash is required")

    if current is None:
        if not allow_missing_create:
            raise ValueError("missing lifecycle Trip in Cosmos")
        body = clean_body(payload)
        body["cosmos_projected_at"] = utc_now_iso()
        return "create", body

    if current.get("user_id") != payload["user_id"]:
        raise ValueError("Cosmos/Gold user_id mismatch")

    current_generation = int(current.get("processing_generation") or 0)
    payload_generation = int(payload["processing_generation"])
    if current_generation > payload_generation:
        return "stale", clean_body(current)

    if current.get("finalization_hash") == payload["finalization_hash"]:
        return "already_published", clean_body(current)

    if (
        current_generation == payload_generation
        and current.get("finalization_hash")
        and current["finalization_hash"] != payload["finalization_hash"]
    ):
        raise ValueError("conflicting finalization_hash for the same generation")

    owner = current.get("result_owner")
    if owner not in (None, "databricks", "mode-detection"):
        raise ValueError(f"Trip is owned by another result producer: {owner}")

    body = clean_body(current)
    body.update(clean_body(payload))
    body["created_at"] = current.get("created_at", payload.get("started_at"))
    body["cosmos_projected_at"] = utc_now_iso()
    return "replace", body

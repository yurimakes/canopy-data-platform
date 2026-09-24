"""Idempotent Cosmos projection used by the Lakeflow ForEachBatch sink."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

_SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: dict) -> dict:
    return {
        key: deepcopy(item)
        for key, item in value.items()
        if key not in _SYSTEM_FIELDS
    }


def merge_projection(
    current: dict | None,
    payload: dict,
    *,
    allow_missing_create: bool,
) -> tuple[str, dict]:
    if payload.get("id") != payload.get("trip_id"):
        raise ValueError("Gold payload id must equal trip_id")
    if not payload.get("user_id"):
        raise ValueError("Gold payload user_id is required")
    if not payload.get("finalization_hash"):
        raise ValueError("Gold payload finalization_hash is required")

    if current is None:
        if not allow_missing_create:
            raise ValueError("missing lifecycle Trip in Cosmos")
        body = _clean(payload)
        body["cosmos_projected_at"] = utc_now_iso()
        return "create", body

    if current.get("user_id") != payload["user_id"]:
        raise ValueError("Cosmos/Gold user_id mismatch")

    current_generation = int(current.get("processing_generation") or 0)
    payload_generation = int(payload["processing_generation"])

    if current_generation > payload_generation:
        return "stale", _clean(current)

    if current.get("finalization_hash") == payload["finalization_hash"]:
        return "already_published", _clean(current)

    if (
        current_generation == payload_generation
        and current.get("finalization_hash")
        and current["finalization_hash"] != payload["finalization_hash"]
    ):
        raise ValueError("conflicting finalization_hash for the same generation")

    owner = current.get("result_owner")
    if owner not in (None, "databricks", "mode-detection"):
        raise ValueError(f"Trip is owned by another result producer: {owner}")

    body = _clean(current)
    body.update(_clean(payload))
    body["created_at"] = current.get("created_at", payload.get("started_at"))
    body["cosmos_projected_at"] = utc_now_iso()
    return "replace", body


def read_current(container, trip_id: str, user_id: str):
    try:
        return container.read_item(item=trip_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None


def project_payload(
    container,
    payload: dict,
    *,
    allow_missing_create: bool,
) -> tuple[str, dict | None]:
    """Project one payload with CAS/read-back semantics; safe for batch retries."""

    for _ in range(5):
        current = read_current(
            container,
            payload["trip_id"],
            payload["user_id"],
        )
        action, body = merge_projection(
            current,
            payload,
            allow_missing_create=allow_missing_create,
        )

        if action in ("stale", "already_published"):
            saved = current
        elif action == "create":
            try:
                saved = container.create_item(body=body)
            except CosmosResourceExistsError:
                continue
        else:
            try:
                saved = container.replace_item(
                    item=current["id"],
                    body=body,
                    etag=current["_etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
            except CosmosHttpResponseError as exc:
                if exc.status_code in (409, 412):
                    continue
                raise

        verified = read_current(
            container,
            payload["trip_id"],
            payload["user_id"],
        )
        if action == "stale":
            return action, verified
        if (
            verified is None
            or verified.get("finalization_hash") != payload["finalization_hash"]
        ):
            raise RuntimeError("Cosmos read-back finalization_hash mismatch")
        return action, verified

    raise RuntimeError("Cosmos projection conflicted repeatedly")


def open_container(
    endpoint: str,
    database: str,
    container_name: str,
    credential: str,
):
    client = CosmosClient(endpoint, credential=credential)
    container = (
        client.get_database_client(database)
        .get_container_client(container_name)
    )
    if container.read()["partitionKey"]["paths"] != ["/user_id"]:
        raise ValueError("Cosmos trips container must use /user_id partition key")
    return container

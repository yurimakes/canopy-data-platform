"""Points-based weekly ranking read API."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential


bp = func.Blueprint()

WEEK_PATTERN = re.compile(r"^\d{4}-W\d{2}$")


def _response(payload, status_code=200):
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _user_id(req: func.HttpRequest) -> str:
    principal = (
        req.headers.get("x-ms-client-principal")
        or req.headers.get("X-MS-CLIENT-PRINCIPAL")
    )

    if principal:
        try:
            decoded = base64.b64decode(principal).decode("utf-8")
            obj = json.loads(decoded)

            claims = obj.get("claims") or []

            preferred = (
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier",
                "http://schemas.microsoft.com/identity/claims/objectidentifier",
                "sub",
                "oid",
            )

            by_type = {
                claim.get("typ"): claim.get("val")
                for claim in claims
                if isinstance(claim, dict)
            }

            for key in preferred:
                if by_type.get(key):
                    return str(by_type[key])

        except Exception:
            pass

    # 개발/E2E 검증에서만 사용
    if os.environ.get(
        "CANOPY_ALLOW_DEV_USER_HEADER",
        "false",
    ).lower() == "true":
        dev_user = (
            req.headers.get("x-canopy-user-id")
            or req.headers.get("X-Canopy-User-Id")
        )

        if dev_user:
            return str(dev_user)

    raise PermissionError("authenticated user required")


def _campaign_id(req: func.HttpRequest) -> str:
    # 실제 서비스에서는 Function App campaign 설정을 사용.
    configured = (
        os.environ.get("CANOPY_CAMPAIGN_ID")
        or os.environ.get("TRIP_CAMPAIGN_ID")
    )

    # E2E test campaign은 dev mode에서만 명시적으로 허용.
    requested = req.params.get("campaign_id")

    if (
        requested
        and os.environ.get(
            "CANOPY_ALLOW_DEV_USER_HEADER",
            "false",
        ).lower() == "true"
        and requested.startswith("pipeline_test_")
    ):
        return requested

    if configured:
        return configured

    raise RuntimeError("campaign not configured")


def _week(req: func.HttpRequest) -> str:
    value = req.params.get("week")

    if value:
        if not WEEK_PATTERN.fullmatch(value):
            raise ValueError("week must use YYYY-Www format")
        return value

    now = datetime.now()
    year, week, _ = now.isocalendar()

    return f"{year}-W{week:02d}"


def _container():
    endpoint = (
        os.environ.get("CANOPY_COSMOS_ENDPOINT")
        or os.environ.get("COSMOS_ENDPOINT")
    )

    if not endpoint:
        raise RuntimeError("Cosmos endpoint not configured")

    database_name = (
        os.environ.get("CANOPY_COSMOS_DATABASE")
        or os.environ.get("COSMOS_DATABASE")
        or "canopy-db"
    )

    client = CosmosClient(
        endpoint,
        credential=DefaultAzureCredential(),
    )

    return (
        client
        .get_database_client(database_name)
        .get_container_client("ranking")
    )


@bp.route(
    route="users/me/ranking",
    methods=["GET"],
    auth_level=func.AuthLevel.ADMIN if os.getenv('CANOPY_COMMUNITY_ENABLED','false').lower()=='true' else func.AuthLevel.FUNCTION,
)
def ranking_get(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_id = _user_id(req)
        campaign_id = _campaign_id(req)
        week = _week(req)

        try:
            doc = _container().read_item(
                item=week,
                partition_key=campaign_id,
            )
        except CosmosResourceNotFoundError:
            return _response(
                {
                    "status": "empty",
                    "week": week,
                    "personal": [],
                    "department": [],
                }
            )

        if doc.get("schema_version") != "ranking-points-v1":
            return _response(
                {
                    "status": "error",
                    "code": "unsupported_ranking_schema",
                },
                409,
            )

        personal = []

        for row in doc.get("personal_ranking", []):
            personal.append(
                {
                    # internal user_id는 응답으로 노출하지 않음
                    "id": f"rank-{row['rank']}",
                    "name": row.get("nickname") or "사용자",
                    "rank": int(row["rank"]),
                    "points": float(row["score_points"]),
                    "is_me": row.get("user_id") == user_id,
                }
            )

        return _response(
            {
                "status": "ready",
                "week": doc["week"],
                "updated_at": doc.get("generated_at"),
                "score_unit": "points",
                "personal": personal,
                "department": [],
            }
        )

    except PermissionError:
        return _response(
            {
                "status": "error",
                "code": "unauthorized",
            },
            401,
        )

    except ValueError as exc:
        return _response(
            {
                "status": "error",
                "code": "invalid_request",
                "message": str(exc),
            },
            400,
        )

    except Exception as exc:
        logging.exception(
            "ranking_get_failed error_type=%s",
            type(exc).__name__,
        )

        return _response(
            {
                "status": "error",
                "code": "service_unavailable",
            },
            503,
        )

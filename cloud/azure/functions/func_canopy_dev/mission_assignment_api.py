"""Weekly mission assignment/retrieval routes for the existing Azure Function App."""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
from azure.identity import DefaultAzureCredential

from mission_engine import assign_for_week, get_for_week, load_mission_policy

bp = func.Blueprint()
BASE_DIR = Path(__file__).resolve().parent
MISSION_POLICY = load_mission_policy(BASE_DIR / "mission_policy.yaml")


class MissionApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(message)


def _response(payload, status_code=200):
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _principal_user_id(headers) -> str:
    principal = headers.get("x-ms-client-principal") or headers.get("X-MS-CLIENT-PRINCIPAL")
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
            by_type = {claim.get("typ"): claim.get("val") for claim in claims if isinstance(claim, dict)}
            for key in preferred:
                if by_type.get(key):
                    return str(by_type[key])
        except Exception as exc:
            raise MissionApiError(401, "invalid_principal", "authenticated principal header is invalid") from exc

    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        dev_user = headers.get("x-canopy-user-id") or headers.get("X-Canopy-User-Id")
        if dev_user:
            return str(dev_user)

    raise MissionApiError(401, "unauthorized", "authenticated user is required")


def _campaign_id() -> str:
    value = os.environ.get("CANOPY_CAMPAIGN_ID")
    if value:
        return value
    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        return "local-test"
    raise MissionApiError(503, "campaign_not_configured", "campaign is not configured")


def _parse_week_date(raw: str | None, tz_name: str) -> date:
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise MissionApiError(400, "invalid_week", "week must be YYYY-MM-DD") from exc
    return datetime.now(ZoneInfo(tz_name)).date()


def _week_bounds(raw_week: str | None):
    tz_name = os.environ.get("CANOPY_CAMPAIGN_TIMEZONE", "Asia/Seoul")
    try:
        ref = _parse_week_date(raw_week, tz_name)
        monday = ref - timedelta(days=ref.weekday())
        week_end = monday + timedelta(days=7)
        return monday.isoformat(), week_end.isoformat()
    except MissionApiError:
        raise
    except Exception as exc:
        raise MissionApiError(503, "timezone_not_configured", "campaign timezone is invalid") from exc


class CosmosMissionRepository:
    def __init__(self):
        endpoint = os.environ.get("CANOPY_COSMOS_ENDPOINT") or os.environ.get("COSMOS_ENDPOINT")
        if not endpoint:
            raise RuntimeError("CANOPY_COSMOS_ENDPOINT or COSMOS_ENDPOINT is required")
        credential = DefaultAzureCredential()
        client = CosmosClient(endpoint, credential=credential)
        database_name = os.environ.get("CANOPY_COSMOS_DATABASE") or os.environ.get("COSMOS_DATABASE", "canopy-db")
        database = client.get_database_client(database_name)
        profile_name = os.environ.get("CANOPY_COSMOS_MISSION_PROFILE_CONTAINER", "mission-profiles")
        assignment_name = os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")
        self.profile_container = database.get_container_client(profile_name)
        self.assignment_container = database.get_container_client(assignment_name)

    @staticmethod
    def pk(campaign_id: str, user_id: str) -> str:
        return f"{campaign_id}:{user_id}"

    def get_latest_profile(self, campaign_id: str, user_id: str):
        item_id = f"mission-profile-latest:{campaign_id}:{user_id}"
        try:
            return self.profile_container.read_item(item=item_id, partition_key=self.pk(campaign_id, user_id))
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    def get_assignment(self, campaign_id: str, user_id: str, week_start: str):
        from mission_engine import assignment_id

        aid = assignment_id(campaign_id, user_id, week_start)
        try:
            return self.assignment_container.read_item(item=aid, partition_key=self.pk(campaign_id, user_id))
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    def create_assignment(self, item):
        try:
            return self.assignment_container.create_item(item)
        except cosmos_exceptions.CosmosResourceExistsError:
            return self.assignment_container.read_item(item=item["id"], partition_key=item["pk"])


def _assign(repo, *, user_id: str, campaign_id: str, week_start: str, week_end: str):
    return assign_for_week(
        repo,
        MISSION_POLICY,
        user_id=user_id,
        campaign_id=campaign_id,
        week_start=week_start,
        week_end=week_end,
        now_iso=datetime.now(timezone.utc).isoformat(),
    )


def _handle(req: func.HttpRequest, *, assign: bool) -> func.HttpResponse:
    try:
        user_id = _principal_user_id(req.headers)
        campaign_id = _campaign_id()
        week_start, week_end = _week_bounds(req.params.get("week"))
        repo = CosmosMissionRepository()

        if assign:
            result = _assign(
                repo,
                user_id=user_id,
                campaign_id=campaign_id,
                week_start=week_start,
                week_end=week_end,
            )
        else:
            result = get_for_week(
                repo,
                user_id=user_id,
                campaign_id=campaign_id,
                week_start=week_start,
                week_end=week_end,
            )
            # The iPhone can use one read endpoint. If the week's deterministic
            # assignment has not been issued yet, first read performs an idempotent
            # lazy issue from the immediately previous completed profile.
            if result.get("status") == "collecting" and result.get("reason") == "assignment_not_issued":
                result = _assign(
                    repo,
                    user_id=user_id,
                    campaign_id=campaign_id,
                    week_start=week_start,
                    week_end=week_end,
                )

        return _response(result, 200)
    except MissionApiError as exc:
        return _response({"status": "error", "code": exc.code, "message": str(exc)}, exc.status)
    except Exception as exc:
        logging.exception("mission_api_failed error_type=%s", type(exc).__name__)
        return _response(
            {"status": "error", "code": "service_unavailable", "message": "Mission service unavailable"},
            503,
        )


@bp.route(route="users/me/missions/assign", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def mission_assign(req: func.HttpRequest) -> func.HttpResponse:
    return _handle(req, assign=True)


@bp.route(route="users/me/missions", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def mission_get(req: func.HttpRequest) -> func.HttpResponse:
    return _handle(req, assign=False)

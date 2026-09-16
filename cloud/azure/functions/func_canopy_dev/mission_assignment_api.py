"""Weekly mission offer, selection, assignment, and retrieval routes."""
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

from mission_engine import (
    MissionSelectionError,
    assignment_id,
    get_week_state,
    load_mission_policy,
    offer_set_id,
    select_mission,
)

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
        return monday.isoformat(), (monday + timedelta(days=7)).isoformat()
    except MissionApiError:
        raise
    except Exception as exc:
        raise MissionApiError(503, "timezone_not_configured", "campaign timezone is invalid") from exc


class CosmosMissionRepository:
    def __init__(self):
        endpoint = os.environ.get("CANOPY_COSMOS_ENDPOINT") or os.environ.get("COSMOS_ENDPOINT")
        if not endpoint:
            raise RuntimeError("CANOPY_COSMOS_ENDPOINT or COSMOS_ENDPOINT is required")
        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        database_name = os.environ.get("CANOPY_COSMOS_DATABASE") or os.environ.get("COSMOS_DATABASE", "canopy-db")
        database = client.get_database_client(database_name)
        self.profile_container = database.get_container_client(
            os.environ.get("CANOPY_COSMOS_MISSION_PROFILE_CONTAINER", "mission-profiles")
        )
        self.mission_container = database.get_container_client(
            os.environ.get("CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER", "mission-assignments")
        )

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
        aid = assignment_id(campaign_id, user_id, week_start)
        try:
            return self.mission_container.read_item(item=aid, partition_key=self.pk(campaign_id, user_id))
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    def get_offer_set(self, campaign_id: str, user_id: str, week_start: str):
        oid = offer_set_id(campaign_id, user_id, week_start)
        try:
            return self.mission_container.read_item(item=oid, partition_key=self.pk(campaign_id, user_id))
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    def create_offer_set(self, item):
        try:
            return self.mission_container.create_item(item)
        except cosmos_exceptions.CosmosResourceExistsError:
            return self.mission_container.read_item(item=item["id"], partition_key=item["pk"])

    def create_assignment(self, item):
        try:
            return self.mission_container.create_item(item)
        except cosmos_exceptions.CosmosResourceExistsError:
            return self.mission_container.read_item(item=item["id"], partition_key=item["pk"])

    def mark_offer_selected(self, offer, mission_template_id: str, selected_at: str):
        latest = self.mission_container.read_item(item=offer["id"], partition_key=offer["pk"])
        if latest.get("selected_mission_template_id"):
            return latest
        latest["selected_mission_template_id"] = mission_template_id
        latest["selected_at"] = selected_at
        return self.mission_container.replace_item(item=latest["id"], body=latest)


def _request_context(req: func.HttpRequest):
    user_id = _principal_user_id(req.headers)
    campaign_id = _campaign_id()
    week_start, week_end = _week_bounds(req.params.get("week"))
    return user_id, campaign_id, week_start, week_end, CosmosMissionRepository()


def _get(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_id, campaign_id, week_start, week_end, repo = _request_context(req)
        result = get_week_state(
            repo,
            MISSION_POLICY,
            user_id=user_id,
            campaign_id=campaign_id,
            week_start=week_start,
            week_end=week_end,
            now_iso=datetime.now(timezone.utc).isoformat(),
        )
        return _response(result)
    except MissionApiError as exc:
        return _response({"status": "error", "code": exc.code, "message": str(exc)}, exc.status)
    except Exception as exc:
        logging.exception("mission_get_failed error_type=%s", type(exc).__name__)
        return _response({"status": "error", "code": "service_unavailable"}, 503)


def _select(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_id, campaign_id, week_start, week_end, repo = _request_context(req)
        try:
            body = req.get_json()
        except ValueError as exc:
            raise MissionApiError(400, "invalid_json", "body must be JSON") from exc
        if not isinstance(body, dict):
            raise MissionApiError(400, "invalid_json", "body must be a JSON object")
        requested_offer_set_id = body.get("offer_set_id")
        mission_template_id = body.get("mission_template_id")
        if not isinstance(requested_offer_set_id, str) or not requested_offer_set_id:
            raise MissionApiError(400, "invalid_offer_set_id", "offer_set_id is required")
        if not isinstance(mission_template_id, str) or not mission_template_id:
            raise MissionApiError(400, "invalid_mission_template_id", "mission_template_id is required")

        result = select_mission(
            repo,
            MISSION_POLICY,
            user_id=user_id,
            campaign_id=campaign_id,
            week_start=week_start,
            week_end=week_end,
            requested_offer_set_id=requested_offer_set_id,
            mission_template_id=mission_template_id,
            now_iso=datetime.now(timezone.utc).isoformat(),
        )
        return _response(result, 200)
    except MissionSelectionError as exc:
        return _response({"status": "error", "code": str(exc)}, 409)
    except MissionApiError as exc:
        return _response({"status": "error", "code": exc.code, "message": str(exc)}, exc.status)
    except Exception as exc:
        logging.exception("mission_select_failed error_type=%s", type(exc).__name__)
        return _response({"status": "error", "code": "service_unavailable"}, 503)


@bp.route(route="users/me/missions", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def mission_get(req: func.HttpRequest) -> func.HttpResponse:
    return _get(req)


@bp.route(route="users/me/missions/select", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def mission_select(req: func.HttpRequest) -> func.HttpResponse:
    return _select(req)

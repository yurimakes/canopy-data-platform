"""주간 미션 부여 및 조회 API.

사용자가 미션을 선택하는 단계는 없다. 최초 조회 시 서버가 카테고리별 미션 번들을
결정적으로 생성하고, 이후 같은 주에는 동일한 번들을 반환한다.
"""
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

from mission_engine import bundle_id, get_week_state, load_mission_policy

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
            raise MissionApiError(401, "invalid_principal", "인증 사용자 정보가 올바르지 않습니다.") from exc

    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        dev_user = headers.get("x-canopy-user-id") or headers.get("X-Canopy-User-Id")
        if dev_user:
            return str(dev_user)

    raise MissionApiError(401, "unauthorized", "인증된 사용자가 필요합니다.")


def _campaign_id() -> str:
    # Mission과 Trip이 같은 campaign boundary를 사용한다. 기존 Function App에
    # TRIP_CAMPAIGN_ID가 이미 있으면 별도 CANOPY_CAMPAIGN_ID를 중복 설정하지 않아도 된다.
    value = os.environ.get("CANOPY_CAMPAIGN_ID") or os.environ.get("TRIP_CAMPAIGN_ID")
    if value:
        return value
    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        return "local-test"
    raise MissionApiError(503, "campaign_not_configured", "캠페인 설정이 필요합니다.")


def _parse_week_date(raw: str | None, tz_name: str) -> date:
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise MissionApiError(400, "invalid_week", "week은 YYYY-MM-DD 형식이어야 합니다.") from exc
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
        raise MissionApiError(503, "timezone_not_configured", "캠페인 시간대 설정이 올바르지 않습니다.") from exc


class CosmosMissionRepository:
    def __init__(self):
        endpoint = os.environ.get("CANOPY_COSMOS_ENDPOINT") or os.environ.get("COSMOS_ENDPOINT")
        if not endpoint:
            raise RuntimeError("CANOPY_COSMOS_ENDPOINT 또는 COSMOS_ENDPOINT가 필요합니다.")
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

    def get_bundle(self, campaign_id: str, user_id: str, week_start: str):
        bid = bundle_id(campaign_id, user_id, week_start)
        try:
            return self.mission_container.read_item(item=bid, partition_key=self.pk(campaign_id, user_id))
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    def create_bundle(self, item):
        try:
            return self.mission_container.create_item(item)
        except cosmos_exceptions.CosmosResourceExistsError:
            return self.mission_container.read_item(item=item["id"], partition_key=item["pk"])


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
        return _response({"status": "error", "code": "service_unavailable", "message": "미션 서비스를 사용할 수 없습니다."}, 503)


@bp.route(route="users/me/missions", methods=["GET"], auth_level=func.AuthLevel.ADMIN if os.getenv('CANOPY_COMMUNITY_ENABLED','false').lower()=='true' else func.AuthLevel.FUNCTION)
def mission_get(req: func.HttpRequest) -> func.HttpResponse:
    return _get(req)

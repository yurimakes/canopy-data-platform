"""Authentication and campaign/week parsing shared by new read-only APIs."""
from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


class ApiRequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(message)


def principal_user_id(headers) -> str:
    principal = headers.get("x-ms-client-principal") or headers.get("X-MS-CLIENT-PRINCIPAL")
    if principal:
        try:
            principal += "=" * (-len(principal) % 4)
            obj = json.loads(base64.b64decode(principal).decode("utf-8"))
            claims = obj.get("claims") or []
            by_type = {
                claim.get("typ"): claim.get("val")
                for claim in claims
                if isinstance(claim, dict)
            }
            for key in (
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier",
                "http://schemas.microsoft.com/identity/claims/objectidentifier",
                "sub",
                "oid",
            ):
                if by_type.get(key):
                    return str(by_type[key])
        except Exception as exc:
            raise ApiRequestError(401, "invalid_principal", "인증 사용자 정보가 올바르지 않습니다.") from exc

    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        dev_user = headers.get("x-canopy-user-id") or headers.get("X-Canopy-User-Id")
        if dev_user:
            return str(dev_user)
    raise ApiRequestError(401, "unauthorized", "인증된 사용자가 필요합니다.")


def campaign_id() -> str:
    value = os.environ.get("CANOPY_CAMPAIGN_ID") or os.environ.get("TRIP_CAMPAIGN_ID")
    if value:
        return value
    if os.environ.get("CANOPY_ALLOW_DEV_USER_HEADER", "false").lower() == "true":
        return "local-test"
    raise ApiRequestError(503, "campaign_not_configured", "캠페인 설정이 필요합니다.")


def week_bounds(raw_week: str | None) -> tuple[str, str]:
    timezone_name = os.environ.get("CANOPY_CAMPAIGN_TIMEZONE", "Asia/Seoul")
    try:
        reference = date.fromisoformat(raw_week) if raw_week else datetime.now(ZoneInfo(timezone_name)).date()
    except ValueError as exc:
        raise ApiRequestError(400, "invalid_week", "week은 YYYY-MM-DD 형식이어야 합니다.") from exc
    except Exception as exc:
        raise ApiRequestError(503, "timezone_not_configured", "캠페인 시간대 설정이 올바르지 않습니다.") from exc
    monday = reference - timedelta(days=reference.weekday())
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()


def page_size(raw: str | None, default: int = 50, maximum: int = 100) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiRequestError(400, "invalid_page_size", "page_size는 정수여야 합니다.") from exc
    if value < 1 or value > maximum:
        raise ApiRequestError(400, "invalid_page_size", f"page_size는 1~{maximum}이어야 합니다.")
    return value

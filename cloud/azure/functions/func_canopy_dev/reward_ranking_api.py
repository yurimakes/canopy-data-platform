"""Read-only Functions API for reward ledger and ranking snapshots."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

from canopy_api_context import ApiRequestError, campaign_id, page_size, principal_user_id, week_bounds
from engagement_read_service import EngagementContractError, build_ranking_response, build_reward_response

bp = func.Blueprint()


def _response(payload, status_code=200):
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        mimetype="application/json",
    )


class CosmosEngagementReadRepository:
    """Cosmos serving projection reader; this class never mutates points or ranks."""

    def __init__(self):
        endpoint = os.environ.get("CANOPY_COSMOS_ENDPOINT") or os.environ.get("COSMOS_ENDPOINT")
        if not endpoint:
            raise RuntimeError("CANOPY_COSMOS_ENDPOINT 또는 COSMOS_ENDPOINT가 필요합니다.")
        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        database_name = os.environ.get("CANOPY_COSMOS_DATABASE") or os.environ.get("COSMOS_DATABASE", "canopy-db")
        database = client.get_database_client(database_name)
        self.reward_container = database.get_container_client(
            os.environ.get("CANOPY_COSMOS_REWARD_LEDGER_CONTAINER", "rewards")
        )
        self.ranking_container = database.get_container_client(
            os.environ.get("CANOPY_COSMOS_RANKING_SNAPSHOT_CONTAINER", "ranking-snapshots")
        )

    def reward_records(self, campaign: str, user: str, week: str) -> list[dict]:
        query = (
            "SELECT * FROM c WHERE c.user_id = @user_id AND c.campaign_id = @campaign_id "
            "AND c.week = @week"
        )
        parameters = [
            {"name": "@user_id", "value": user},
            {"name": "@campaign_id", "value": campaign},
            {"name": "@week", "value": week},
        ]
        return list(self.reward_container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user,
        ))

    def latest_ranking_snapshot(self, campaign: str, week: str, scope: str):
        partition_key = f"{campaign}:{week}"
        query = (
            "SELECT TOP 1 * FROM c WHERE c.pk = @pk AND c.campaign_id = @campaign_id "
            "AND c.week_start = @week_start AND c.scope = @scope "
            "ORDER BY c.generated_at DESC"
        )
        parameters = [
            {"name": "@pk", "value": partition_key},
            {"name": "@campaign_id", "value": campaign},
            {"name": "@week_start", "value": week},
            {"name": "@scope", "value": scope},
        ]
        rows = list(self.ranking_container.query_items(
            query=query,
            parameters=parameters,
            partition_key=partition_key,
            max_item_count=1,
        ))
        return rows[0] if rows else None


def _context(req: func.HttpRequest):
    user = principal_user_id(req.headers)
    campaign = campaign_id()
    week_start, week_end = week_bounds(req.params.get("week"))
    size = page_size(req.params.get("page_size"))
    cursor = req.params.get("cursor")
    return user, campaign, week_start, week_end, size, cursor


def _rewards(req: func.HttpRequest, repository=None):
    try:
        user, campaign, week_start, week_end, size, cursor = _context(req)
        repository = repository or CosmosEngagementReadRepository()
        records = repository.reward_records(campaign, user, week_start)
        return _response(build_reward_response(
            records,
            campaign_id=campaign,
            user_id=user,
            week_start=week_start,
            week_end=week_end,
            page_size=size,
            cursor=cursor,
            requested_at=datetime.now(timezone.utc).isoformat(),
        ))
    except ApiRequestError as exc:
        return _response({"status": "error", "code": exc.code, "message": str(exc)}, exc.status)
    except EngagementContractError as exc:
        return _response({"status": "error", "code": str(exc), "message": "조회 조건 또는 저장된 보상 형식이 올바르지 않습니다."}, 400)
    except Exception as exc:
        logging.exception("reward_read_failed error_type=%s", type(exc).__name__)
        return _response({"status": "error", "code": "service_unavailable", "message": "보상 조회 서비스를 사용할 수 없습니다."}, 503)


def _ranking(req: func.HttpRequest, repository=None):
    try:
        user, campaign, week_start, week_end, size, cursor = _context(req)
        scope = req.params.get("scope")
        if scope not in {"individual", "department"}:
            raise ApiRequestError(400, "invalid_scope", "scope는 individual 또는 department여야 합니다.")
        repository = repository or CosmosEngagementReadRepository()
        snapshot = repository.latest_ranking_snapshot(campaign, week_start, scope)
        return _response(build_ranking_response(
            snapshot,
            campaign_id=campaign,
            user_id=user,
            scope=scope,
            week_start=week_start,
            week_end=week_end,
            page_size=size,
            cursor=cursor,
        ))
    except ApiRequestError as exc:
        return _response({"status": "error", "code": exc.code, "message": str(exc)}, exc.status)
    except EngagementContractError as exc:
        return _response({"status": "error", "code": str(exc), "message": "조회 조건 또는 저장된 랭킹 형식이 올바르지 않습니다."}, 400)
    except Exception as exc:
        logging.exception("ranking_read_failed error_type=%s", type(exc).__name__)
        return _response({"status": "error", "code": "service_unavailable", "message": "랭킹 조회 서비스를 사용할 수 없습니다."}, 503)


@bp.route(route="users/me/rewards", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def reward_get(req: func.HttpRequest) -> func.HttpResponse:
    return _rewards(req)


@bp.route(route="rankings", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def ranking_get(req: func.HttpRequest) -> func.HttpResponse:
    return _ranking(req)

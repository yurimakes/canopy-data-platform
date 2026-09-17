import base64
import json

import pytest

from canopy_api_context import ApiRequestError, page_size, principal_user_id, week_bounds
from engagement_read_service import EngagementContractError, build_ranking_response, build_reward_response


WEEK = "2026-09-14"
WEEK_END = "2026-09-21"


def reward(**overrides):
    item = {
        "id": "reward-1",
        "reward_id": "reward-1",
        "user_id": "u1",
        "campaign_id": "c1",
        "week": WEEK,
        "points": 100,
        "reason": "주간 저탄소 이동 보상",
        "policy_version": "reward-policy-v1",
        "status": "paid",
        "created_at": "2026-09-16T09:00:00+00:00",
    }
    item.update(overrides)
    return item


def test_reward_response_uses_paid_and_adjustment_ledger_without_writing():
    records = [
        reward(),
        reward(id="adjustment-1", reward_id="adjustment-1", status="adjustment", points=-20, reason="승인된 조정", created_at="2026-09-17T09:00:00+00:00"),
    ]
    result = build_reward_response(records, campaign_id="c1", user_id="u1", week_start=WEEK, week_end=WEEK_END, page_size=50, cursor=None)
    assert result["status"] == "settled"
    assert result["finalized"] is True
    assert result["total_points"] == 80
    assert result["entries"][0]["status"] == "adjusted"
    assert records[0]["points"] == 100


def test_reward_pagination_keeps_total_for_the_whole_week():
    records = [reward(id=f"r-{index}", reward_id=f"r-{index}", points=index, created_at=f"2026-09-{10 + index:02d}T09:00:00+00:00") for index in range(1, 4)]
    first = build_reward_response(records, campaign_id="c1", user_id="u1", week_start=WEEK, week_end=WEEK_END, page_size=2, cursor=None)
    second = build_reward_response(records, campaign_id="c1", user_id="u1", week_start=WEEK, week_end=WEEK_END, page_size=2, cursor=first["next_cursor"])
    assert first["total_points"] == second["total_points"] == 6
    assert len(first["entries"]) == 2 and len(second["entries"]) == 1
    assert second["next_cursor"] is None


def test_reward_rejects_records_outside_authenticated_boundary():
    with pytest.raises(EngagementContractError, match="reward_boundary_mismatch"):
        build_reward_response([reward(user_id="other")], campaign_id="c1", user_id="u1", week_start=WEEK, week_end=WEEK_END, page_size=50, cursor=None)


def snapshot():
    return {
        "id": "ranking-c1-week-individual-v1",
        "pk": f"c1:{WEEK}",
        "campaign_id": "c1",
        "week_start": WEEK,
        "week_end": WEEK_END,
        "scope": "individual",
        "snapshot_status": "finalized",
        "generated_at": "2026-09-17T00:00:00Z",
        "policy_version": "ranking-policy-v1",
        "aggregation_version": "ranking-build-v1",
        "entries": [
            {"rank": 1, "subject_id": "public-1", "display_name": "이서준", "score": 200, "user_id": "u2"},
            {"rank": 2, "subject_id": "public-me", "display_name": "나", "score": 180, "user_id": "u1"},
        ],
    }


def test_ranking_marks_only_authenticated_user_and_does_not_expose_internal_ids():
    result = build_ranking_response(snapshot(), campaign_id="c1", user_id="u1", scope="individual", week_start=WEEK, week_end=WEEK_END, page_size=50, cursor=None)
    assert result["finalized"] is True
    assert [entry["is_me"] for entry in result["entries"]] == [False, True]
    assert all("user_id" not in entry for entry in result["entries"])


def test_missing_ranking_is_in_progress_and_never_fabricates_zero_rank():
    result = build_ranking_response(None, campaign_id="c1", user_id="u1", scope="department", week_start=WEEK, week_end=WEEK_END, page_size=50, cursor=None)
    assert result["snapshot_status"] == "in_progress"
    assert result["generated_at"] is None
    assert result["entries"] == []


def test_cursor_cannot_be_reused_for_another_snapshot():
    first = build_ranking_response(snapshot(), campaign_id="c1", user_id="u1", scope="individual", week_start=WEEK, week_end=WEEK_END, page_size=1, cursor=None)
    newer = snapshot()
    newer["id"] = "ranking-c1-week-individual-v2"
    with pytest.raises(EngagementContractError, match="invalid_cursor"):
        build_ranking_response(newer, campaign_id="c1", user_id="u1", scope="individual", week_start=WEEK, week_end=WEEK_END, page_size=1, cursor=first["next_cursor"])


def test_principal_and_query_validation(monkeypatch):
    principal = {"claims": [{"typ": "sub", "val": "u1"}]}
    encoded = base64.b64encode(json.dumps(principal).encode()).decode()
    assert principal_user_id({"x-ms-client-principal": encoded}) == "u1"
    assert week_bounds("2026-09-17") == (WEEK, WEEK_END)
    assert page_size("100") == 100
    with pytest.raises(ApiRequestError):
        page_size("101")
    monkeypatch.setenv("CANOPY_ALLOW_DEV_USER_HEADER", "false")
    with pytest.raises(ApiRequestError, match="인증된 사용자"):
        principal_user_id({})

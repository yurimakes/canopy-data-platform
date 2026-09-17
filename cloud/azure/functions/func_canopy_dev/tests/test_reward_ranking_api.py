import json

import azure.functions as func

from reward_ranking_api import _ranking, _rewards


class FakeRepository:
    def __init__(self):
        self.reward_calls = []
        self.ranking_calls = []

    def reward_records(self, campaign, user, week):
        self.reward_calls.append((campaign, user, week))
        return [{
            "id": "r1",
            "reward_id": "r1",
            "user_id": user,
            "campaign_id": campaign,
            "week": week,
            "points": 100,
            "reason": "주간 저탄소 이동 보상",
            "policy_version": "reward-policy-v1",
            "status": "paid",
            "created_at": "2026-09-17T00:00:00Z",
        }]

    def latest_ranking_snapshot(self, campaign, week, scope):
        self.ranking_calls.append((campaign, week, scope))
        return None


def request(path, params=None, headers=None):
    return func.HttpRequest(
        method="GET",
        url=f"https://example.test/api/{path}",
        headers=headers or {},
        params=params or {},
        route_params={},
        body=b"",
    )


def payload(response):
    return json.loads(response.get_body())


def test_reward_route_uses_authenticated_user_not_request_user_id(monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_DEV_USER_HEADER", "true")
    monkeypatch.setenv("CANOPY_CAMPAIGN_ID", "c1")
    repository = FakeRepository()
    response = _rewards(request("users/me/rewards", {"week": "2026-09-17", "user_id": "other"}, {"x-canopy-user-id": "u1"}), repository)
    assert response.status_code == 200
    assert repository.reward_calls == [("c1", "u1", "2026-09-14")]
    assert payload(response)["total_points"] == 100


def test_ranking_route_distinguishes_not_generated_from_error(monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_DEV_USER_HEADER", "true")
    monkeypatch.setenv("CANOPY_CAMPAIGN_ID", "c1")
    response = _ranking(request("rankings", {"week": "2026-09-17", "scope": "department"}, {"x-canopy-user-id": "u1"}), FakeRepository())
    assert response.status_code == 200
    assert payload(response)["snapshot_status"] == "in_progress"
    assert payload(response)["entries"] == []


def test_routes_reject_unauthenticated_and_invalid_scope(monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_DEV_USER_HEADER", "false")
    monkeypatch.setenv("CANOPY_CAMPAIGN_ID", "c1")
    assert _rewards(request("users/me/rewards"), FakeRepository()).status_code == 401

    monkeypatch.setenv("CANOPY_ALLOW_DEV_USER_HEADER", "true")
    response = _ranking(request("rankings", {"scope": "company"}, {"x-canopy-user-id": "u1"}), FakeRepository())
    assert response.status_code == 400
    assert payload(response)["code"] == "invalid_scope"

import pytest

import build_mission_profile as profile
import run_mission_profile_serverless as runner


def test_serverless_runner_requires_named_service_credential(monkeypatch):
    monkeypatch.setattr(profile, "COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
    monkeypatch.delenv(runner.SERVICE_CREDENTIAL_ENV, raising=False)

    with pytest.raises(RuntimeError, match=runner.SERVICE_CREDENTIAL_ENV):
        runner._serverless_cosmos_clients()


def test_serverless_runner_injects_and_restores_cosmos_factory(monkeypatch):
    original = profile._cosmos_clients
    observed = {}

    def fake_run(campaign_id, source_week_start, source_week_end):
        observed["factory"] = profile._cosmos_clients
        observed["args"] = (campaign_id, source_week_start, source_week_end)
        return ["ok"]

    monkeypatch.setattr(profile, "run", fake_run)
    result = runner.run("c1", "2026-09-07", "2026-09-14")

    assert result == ["ok"]
    assert observed["factory"] is runner._serverless_cosmos_clients
    assert observed["args"] == ("c1", "2026-09-07", "2026-09-14")
    assert profile._cosmos_clients is original

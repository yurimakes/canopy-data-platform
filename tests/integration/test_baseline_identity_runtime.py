import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud/azure/pipelines/databricks"))
from baseline_eligibility import load_identities, observation_context


class IdentityAndRuntimeTests(unittest.TestCase):
    def test_cosmos_partition_reads_and_membership_priority(self):
        client = MagicMock()
        db = client.get_database_client.return_value
        users, members = MagicMock(), MagicMock()
        db.get_container_client.side_effect = lambda name: {"users": users, "campaign_memberships": members}[name]
        users.read_item.return_value = {"id": "u", "user_id": "u", "created_at": "2020-01-01T00:00:00Z", "private_profile": "not needed"}
        members.read_item.return_value = {"id": "c", "user_id": "u", "campaign_id": "c", "joined_at": "2026-09-01T00:00:00Z"}
        with patch.dict(os.environ, {"CANOPY_COSMOS_DATABASE": "canopy-db"}, clear=True):
            data = load_identities(campaign_id="c", user_ids=["u", "u"], client=client)
        users.read_item.assert_called_once_with(item="u", partition_key="u")
        members.read_item.assert_called_once_with(item="c", partition_key="u")
        self.assertNotIn("private_profile", data["users"][0])
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", data), (7, "membership.joined_at", None))
        db.create_container_if_not_exists.assert_not_called()

    def test_missing_cosmos_records_are_collecting_not_created(self):
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        client = MagicMock()
        client.get_database_client.return_value.get_container_client.return_value.read_item.side_effect = CosmosResourceNotFoundError(message="missing")
        with patch.dict(os.environ, {"CANOPY_COSMOS_DATABASE": "canopy-db"}, clear=True):
            data = load_identities(campaign_id="c", user_ids=["u"], client=client)
        self.assertEqual(data, {"users": [], "memberships": []})

    def test_schemas_and_identity_snapshot_scope(self):
        from jsonschema import Draft202012Validator, FormatChecker
        user = {"id": "u", "user_id": "u", "created_at": "2026-09-01T00:00:00Z"}
        membership = {"id": "c", "user_id": "u", "campaign_id": "c", "joined_at": "2026-09-01T00:00:00Z"}
        for name, value in [("user", user), ("campaign_membership", membership)]:
            schema = json.loads((ROOT / f"shared/schemas/{name}.schema.json").read_text())
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identities.json"
            path.write_text(json.dumps({"users": [user], "memberships": [membership, dict(membership, id="other", campaign_id="other")]}))
            data = load_identities(path, campaign_id="c", user_ids=["u"])
            self.assertEqual(data["memberships"], [membership])

    def test_packaged_yaml_loads_outside_repository_and_weekly_job_not_included(self):
        spec = importlib.util.spec_from_file_location("pack", ROOT / "tools/azure/package_baseline_eligibility.py")
        pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack)
        with tempfile.TemporaryDirectory() as tmp:
            archive = pack.package(Path(tmp) / "bundle.zip", "/Workspace/test/canopy")
            with zipfile.ZipFile(archive) as z:
                self.assertFalse(any("build_weekly_summary" in n or "sync_confirmed_trips" in n for n in z.namelist()))
                tasks = json.loads(z.read("baseline_eligibility_tasks.json"))["tasks"]
                self.assertEqual(tasks[1]["depends_on"], [{"task_key": "build_personal_baseline"}])
                z.extractall(Path(tmp) / "deployed")
            runner = Path(tmp) / "deployed" / pack.RUNTIME / "run_eligible_baselines.py"
            env = dict(os.environ)
            env.pop("CANOPY_BASELINE_ELIGIBILITY_PATH", None)
            result = subprocess.check_output([sys.executable, str(runner), "--check-config"], cwd=tmp, env=env)
            self.assertEqual(json.loads(result)["eligibility_policy_version"], "eligibility-v1")



if __name__ == "__main__":
    unittest.main()

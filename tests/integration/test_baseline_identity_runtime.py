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
from baseline_eligibility import load_eligibility_policy, load_identities, observation_context


class IdentityAndRuntimeTests(unittest.TestCase):
    def test_storage_policy_is_read_without_local_fallback(self):
        uri = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/config/baseline/eligibility-v1/baseline_eligibility.yaml"
        content = (ROOT / "shared/configs/baseline_eligibility.yaml").read_text(encoding="utf-8")
        with patch("pyspark.sql.SparkSession") as session:
            spark = session.builder.getOrCreate.return_value
            collect = spark.read.option.return_value.text.return_value.limit.return_value.collect
            collect.return_value = [{"value": content}]
            self.assertEqual(load_eligibility_policy(uri)["policy_version"], "eligibility-v1")
            spark.read.option.return_value.text.assert_called_once_with(uri)
            collect.return_value = []
            with self.assertRaises(ValueError):
                load_eligibility_policy(uri)
            collect.side_effect = PermissionError("Storage access denied")
            with self.assertRaises(PermissionError):
                load_eligibility_policy(uri)

    def test_cosmos_partition_reads_and_membership_priority(self):
        client = MagicMock()
        db = client.get_database_client.return_value
        users = MagicMock()
        db.get_container_client.return_value = users
        users.read_item.return_value = {"id": "u", "user_id": "u", "created_at": "2020-01-01T00:00:00Z",
            "campaign_id": "c", "campaign_joined_at": "2026-09-01T00:00:00Z", "private_profile": "not needed"}
        with patch.dict(os.environ, {"CANOPY_COSMOS_DATABASE": "canopy-db"}, clear=True):
            data = load_identities(campaign_id="c", user_ids=["u", "u"], client=client)
        users.read_item.assert_called_once_with(item="u", partition_key="u")
        db.get_container_client.assert_called_once_with("users")
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

    def test_user_campaign_date_never_falls_back_to_signup(self):
        user = {"user_id": "u", "created_at": "2020-01-01T00:00:00Z", "campaign_id": "c"}
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", {"users": [user]}),
                         (None, None, "joined_at_missing"))
        user["campaign_joined_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", {"users": [user]})[0], 7)
        self.assertEqual(observation_context("u", "other", "2026-09-08T00:00:00Z", {"users": [user]})[2], "joined_at_missing")

    def test_sync_preserves_adls_contract_from_users(self):
        from sync_campaign_membership import _strip_membership, read_memberships_from_cosmos
        item = {"user_id": "u", "campaign_id": "c", "created_at": "2026-09-01T00:00:00Z",
                "campaign_joined_at": "2026-09-01T00:00:00Z", "department_id": "dept"}
        self.assertEqual(_strip_membership(item), {"user_id": "u", "campaign_id": "c",
            "joined_at": item["campaign_joined_at"], "left_at": None, "department_id": "dept"})
        with patch("sync_campaign_membership._get_container") as container:
            container.return_value.query_items.return_value = [item]
            self.assertEqual(read_memberships_from_cosmos("c"), [item])
            self.assertEqual(container.return_value.query_items.call_args.kwargs["parameters"],
                             [{"name": "@campaign_id", "value": "c"}])
        with self.assertRaises(ValueError):
            _strip_membership(dict(item, campaign_joined_at="2026-09-02T00:00:00Z"))
        equivalent = dict(item, campaign_joined_at="2026-09-01T09:00:00+09:00")
        self.assertEqual(_strip_membership(equivalent)["joined_at"], equivalent["campaign_joined_at"])
        del item["campaign_joined_at"]
        with self.assertRaises(ValueError):
            _strip_membership(item)

    def test_user_schema_requires_campaign_participation_date(self):
        from jsonschema import Draft202012Validator, FormatChecker, ValidationError
        schema = json.loads((ROOT / "shared/schemas/user.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        user = {"id": "u", "user_id": "u", "created_at": "2020-01-01T00:00:00Z", "campaign_id": "c"}
        with self.assertRaises(ValidationError):
            validator.validate(user)
        user["campaign_joined_at"] = "2026-09-01T00:00:00Z"
        validator.validate(user)

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

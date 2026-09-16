"""Pipeline contracts and recovery without Azure resources or real ML."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud/azure/pipelines/databricks"))
import finalize_trip_pipeline as pipeline
from services.cosmos_service import SQLiteTripStore, Conflict
from services.trip_processor import ProcessingError


def envelope():
    return {"provider": "mock", "completed_at": "2026-09-16T01:11:00+00:00", "trip": {
        "trip_id": "pipeline_test_trip_1", "user_id": "pipeline_test_user_1",
        "campaign_id": "pipeline_test_campaign_1", "status": "processing", "processing_generation": 1,
        "started_at": "2026-09-16T01:00:00+00:00", "ended_at": "2026-09-16T01:10:00+00:00"}}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteTripStore(str(Path(self.temp.name) / "trips.sqlite"))
        self.document = pipeline.build_final_trip(envelope())

    def test_existing_carbon_contract_and_stable_replay(self):
        self.assertEqual(self.document["carbon"]["kg_co2e"], .778224)
        self.assertEqual(self.document["confirmed_trip"]["total_distance_m"], 7000)
        self.assertEqual(self.document["confirmed_trip"]["bus_distance_m"], 6200)
        self.assertEqual(self.document, pipeline.build_final_trip(envelope()))
        self.assertEqual(self.document["carbon"]["unit"], "kgCO2e")
        self.assertEqual(len(self.document["segments"]), 3)

    def test_wait_timeout_preserves_results_and_retries_idempotently(self):
        doc = {**self.document, "status": "processing", "result_owner": "databricks"}
        self.store.create(doc)
        wait = {"user_id": doc["user_id"], "trip_id": doc["trip_id"],
                "processing_generation": doc["processing_generation"], "status": "timed_out",
                "reason": "waiting_for_prediction_coverage"}
        self.assertEqual(pipeline.publish_wait_failure(self.store, wait), "published")
        self.assertEqual(pipeline.publish_wait_failure(self.store, wait), "already_published")
        saved = self.store.read(doc["trip_id"], doc["user_id"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["failed_step"], "wait_for_ml")
        self.assertEqual(saved["segments"], doc["segments"])
        self.assertEqual(pipeline.publish_wait_failure(self.store, {**wait, "processing_generation": 99}), "stale_wait")

    def test_serverless_exec_without_file_global(self):
        path = ROOT / "cloud/azure/pipelines/databricks/finalize_trip_pipeline.py"
        namespace = {"__name__": "serverless_test"}
        exec(compile(path.read_bytes(), str(path), "exec"), namespace)
        self.assertEqual(namespace["ROOT"], ROOT)

    def test_external_result_uses_exact_same_boundary(self):
        value = envelope()
        value["provider"] = "external"
        value["result"] = pipeline.ConfirmationFixtureProcessor().process_trip(value["trip"])
        value["result"]["model_version"] = "team_model_v1"
        actual = pipeline.build_final_trip(value)
        self.assertFalse(actual["is_mock"])
        self.assertEqual(actual["carbon"], self.document["carbon"])
        value["result"]["segments"][0]["distance_m"] = -1
        with self.assertRaises(ProcessingError):
            pipeline.build_final_trip(value)

    def test_mock_cannot_use_real_identity(self):
        value = envelope()
        value["trip"]["trip_id"] = "real_trip"
        with self.assertRaises(ValueError):
            pipeline.build_final_trip(value)

    def test_phone_mock_requires_explicit_test_campaign(self):
        value = envelope()
        value["trip"]["trip_id"] = "phone-server-generated-uuid"
        self.assertTrue(pipeline.build_final_trip(value, allow_test_trip=True)["is_mock"])
        value["trip"]["campaign_id"] = "production_campaign"
        with self.assertRaises(ValueError):
            pipeline.build_final_trip(value, allow_test_trip=True)

    def test_repeated_projection_preserves_feedback(self):
        pipeline.publish_cosmos(self.store, self.document, True)
        saved = self.store.read(self.document["id"], self.document["user_id"])
        saved["feedback_id"] = "feedback_1"
        self.store.replace(saved)
        self.assertEqual(pipeline.publish_cosmos(self.store, self.document, True), "already_published")
        self.assertEqual(self.store.read(saved["id"], saved["user_id"])["feedback_id"], "feedback_1")

    def test_existing_functions_result_is_not_overwritten(self):
        current = {**self.document, "finalization_hash": "another_worker"}
        self.store.create(current)
        with self.assertRaises(ValueError):
            pipeline.publish_cosmos(self.store, self.document)

    def test_assigned_lifecycle_keeps_unrelated_fields(self):
        trip = {**envelope()["trip"], "id": self.document["id"], "result_owner": "databricks",
                "device_id": "phone", "feedback_id": "keep_me"}
        self.store.create(trip)
        pipeline.publish_cosmos(self.store, self.document)
        saved = self.store.read(trip["id"], trip["user_id"])
        self.assertEqual(saved["device_id"], "phone")
        self.assertEqual(saved["feedback_id"], "keep_me")
        self.assertEqual(saved["status"], "ready")

    def test_missing_production_trip_and_stale_generation_are_rejected(self):
        with self.assertRaises(ValueError):
            pipeline.publish_cosmos(self.store, self.document)
        trip = {**envelope()["trip"], "id": self.document["id"], "processing_generation": 2}
        self.store.create(trip)
        with self.assertRaises(ValueError):
            pipeline.publish_cosmos(self.store, self.document)

    def test_failed_cosmos_can_retry_saved_gold_document(self):
        class Unavailable:
            def read(self, *args):
                raise ConnectionError("offline")
        payload = pipeline.canonical(self.document)
        with self.assertRaises(ConnectionError):
            pipeline.publish_cosmos(Unavailable(), self.document, True)
        import json
        saved_gold = json.loads(payload)
        self.assertEqual(pipeline.publish_cosmos(self.store, saved_gold, True), "published")

    def test_corrupt_gold_is_not_published(self):
        self.document["carbon"]["kg_co2e"] = 100
        with self.assertRaises(ValueError):
            pipeline.publish_cosmos(self.store, self.document, True)

    def test_gold_transaction_conflicts_retry_same_document_only(self):
        from unittest.mock import patch
        with patch.object(pipeline, "_save_gold", side_effect=[RuntimeError("[DELTA_CONCURRENT_APPEND]"), self.document]) as write:
            with patch.object(pipeline.time, "sleep"):
                self.assertEqual(pipeline.save_gold(None, "test-path", self.document), self.document)
            self.assertEqual(write.call_args_list[0], write.call_args_list[1])
        with patch.object(pipeline, "_save_gold", side_effect=ValueError("bad schema")) as write:
            with self.assertRaises(ValueError):
                pipeline.save_gold(None, "test-path", self.document)
            self.assertEqual(write.call_count, 1)

    def test_concurrent_feedback_is_preserved_after_cas_retry(self):
        trip = {**envelope()["trip"], "id": self.document["id"], "result_owner": "databricks"}
        self.store.create(trip)
        store = self.store
        replace = store.replace
        raced = False
        def racing_replace(item):
            nonlocal raced
            if not raced:
                raced = True
                fresh = store.read(item["id"], item["user_id"])
                replace({**fresh, "feedback_id": "arrived_during_publish"})
                raise Conflict()
            return replace(item)
        store.replace = racing_replace
        pipeline.publish_cosmos(store, self.document)
        self.assertEqual(store.read(trip["id"], trip["user_id"])["feedback_id"], "arrived_during_publish")

    def test_package_contains_only_second_pipeline_tasks(self):
        import json
        import zipfile
        sys.path.insert(0, str(ROOT / "tools/azure"))
        from package_trip_pipeline import package, FILES
        path = package(Path(self.temp.name) / "pipeline.zip", "/Workspace/Users/test/pipeline",
                       "abfss://curated@example.dfs.core.windows.net/pipeline_test/run1",
                       "https://example.documents.azure.com")
        with zipfile.ZipFile(path) as archive:
            for name in FILES:
                self.assertEqual(archive.read(name), (ROOT / name).read_bytes())
            job = json.loads(archive.read("trip_finalization_job.json"))
            self.assertEqual([t["task_key"] for t in job["tasks"]], ["finalize_gold", "publish_cosmos"])
            self.assertEqual(job["tasks"][1]["depends_on"], [{"task_key": "finalize_gold"}])
            self.assertNotIn("cloud/azure/pipelines/databricks/build_weekly_summary.py", archive.namelist())
            self.assertNotIn("schedule", job)
            self.assertEqual(job["max_concurrent_runs"], 1)

    def test_phone_job_package_connects_end_to_existing_runner(self):
        import json
        import zipfile
        sys.path.insert(0, str(ROOT / "tools/azure"))
        from package_trip_pipeline import package
        path = package(Path(self.temp.name) / "phone.zip", "/Workspace/Users/test/pipeline",
                       "abfss://curated@example.dfs.core.windows.net/pipeline_test/run1",
                       "https://example.documents.azure.com", "existing-scope", "cosmos-key", iphone=True)
        with zipfile.ZipFile(path) as archive:
            job = json.loads(archive.read("trip_finalization_job.json"))
            self.assertEqual(len(job["tasks"]), 1)
            task = job["tasks"][0]["spark_python_task"]
            self.assertTrue(task["python_file"].endswith("/trip_job.py"))
            self.assertIn("{{job.parameters.end_event}}", task["parameters"])
            self.assertEqual(job["max_concurrent_runs"], 3)
            self.assertNotIn("schedule", job)

    def test_deployed_patch_preserves_team_bytes_and_worker_permissions(self):
        import zipfile
        sys.path.insert(0, str(ROOT / "tools/azure"))
        from package_trip_api import patch_deployed
        source, target = (Path(self.temp.name) / n for n in ("live.zip", "updated.zip"))
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("function_app.py", b"# existing team entrypoint\n")
            archive.writestr("services/runtime.py", b"# old module\n")
        patch_deployed(source, target, ROOT)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(archive.read("function_app.py"), b"# existing team entrypoint\n")
            for info in archive.infolist():
                if info.filename != "function_app.py":
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o644)


@unittest.skipUnless(os.environ.get("CANOPY_TEST_SPARK") == "1", "set CANOPY_TEST_SPARK=1 with a full JDK")
class WeeklyContractTests(unittest.TestCase):
    def test_existing_weekly_reads_gold_shape_without_cosmos(self):
        from pyspark.sql import SparkSession
        import build_weekly_summary as weekly
        spark = SparkSession.builder.master("local[2]").appName("trip-contract-test").config(
            "spark.sql.shuffle.partitions", "2").config("spark.ui.enabled", "false").getOrCreate()
        try:
            frame = pipeline.gold_frame(spark, pipeline.build_final_trip(envelope()))
            personal = weekly.build_personal_weekly(weekly.assign_week(frame)).cache()
            row = personal.first()
            self.assertEqual(row.trip_count, 1)
            self.assertEqual(row.total_distance_m, 7000)
            self.assertAlmostEqual(row.total_kg_co2e, .778224)
            self.assertEqual(row.bus_distance_m, 6200)
            self.assertEqual(row.week, "2026-W38")
            self.assertEqual(weekly.build_campaign_weekly(personal).first().total_trip_count, 1)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()

"""Local evidence only: no Azure resource, real phone, or real GPS is accessed."""
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from services.cosmos_service import SQLiteTripStore
from services.mock_trip_processor import MockTripProcessor
from services.trip_processor import ProcessingError
from services.trip_service import TripService
from services.runtime import authenticate
from trip_routes import dispatch, bp

TOKEN = "local-test-token-" + "x" * 32


class TripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "trips.sqlite")
        self.now = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
        self.store = SQLiteTripStore(self.path)
        self.processor = MockTripProcessor()
        self.api = TripService(self.store, self.processor, lambda: self.now, grace_seconds=0)
        self.env = patch.dict(os.environ, {"APP_ENV": "development", "TRIP_AUTH_MODE": "local",
                                          "TRIP_LOCAL_TOKENS": json.dumps({"alice": TOKEN}), "WEBSITE_HOSTNAME": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def request(self, method, path, body=None, token=TOKEN):
        headers = {"authorization": "Bearer " + token} if token else {}
        return dispatch(method, "/api" + path, headers, json.dumps(body or {}).encode(), self.api)

    def start(self, request_id="start-001"):
        return self.request("POST", "/trips/start", {"request_id": request_id, "device_id": "phone-001"})

    def stop(self, trip, body=None):
        self.now += timedelta(seconds=600)
        return self.request("POST", f"/trips/{trip['trip_id']}/stop", body)

    def test_1_start_collecting_persisted(self):
        status, trip = self.start()
        self.assertEqual(status, 201)
        self.assertEqual(trip["status"], "collecting")
        saved = self.store.read(trip["trip_id"], "alice")
        self.assertEqual(saved["user_id"], "alice")
        self.assertEqual(saved["segments"], [])
        self.assertEqual(saved["campaign_id"], "local-test")

    def test_2_duplicate_concurrent_start_same_trip(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.start(), range(8)))
        self.assertEqual(sum(status == 201 for status, _ in responses), 1)
        self.assertEqual(len({trip["trip_id"] for _, trip in responses}), 1)
        self.assertEqual(len({trip["started_at"] for _, trip in responses}), 1)

    def test_3_stop_processing_then_persisted_ready_after_restart(self):
        _, trip = self.start()
        status, stopped = self.stop(trip)
        self.assertEqual((status, stopped["status"]), (202, "processing"))
        restarted = TripService(SQLiteTripStore(self.path), self.processor, lambda: self.now)
        self.assertEqual(restarted.process_pending(), 1)
        saved = restarted.get(trip["trip_id"], "alice")
        self.assertEqual(saved["status"], "ready")
        self.assertEqual([s["mode"] for s in saved["segments"]], ["walk", "bus", "walk"])
        self.assertTrue(saved["is_mock"])
        first = saved["segments"][0]
        self.assertEqual(first["model_prediction"], first["mode"])
        self.assertEqual(first["started_at"], first["start_time"])
        self.assertIsNone(first["confirmed_mode"])
        self.assertFalse(first["corrected"])

    def test_4_get_ready_segments_and_id(self):
        _, trip = self.start()
        self.stop(trip)
        self.api.process_pending()
        status, result = self.request("GET", f"/trips/{trip['trip_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result["trip_id"], trip["trip_id"])
        self.assertEqual(result["model_version"], "mock_v1")
        self.assertEqual(len(result["segments"]), 3)
        self.assertNotIn("_etag", result)

    def test_5_duplicate_stop_and_workers_do_not_rerun(self):
        _, trip = self.start()
        self.stop(trip)
        with patch.object(self.processor, "process_trip", wraps=self.processor.process_trip) as process:
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda _: self.api.process_pending(), range(5)))
            self.stop(trip)
            self.api.process_pending()
            self.assertEqual(process.call_count, 1)
        saved = self.api.get(trip["trip_id"], "alice")
        self.assertEqual(saved["processing_generation"], 1)

    def test_6_failure_step_and_explicit_idempotent_retry(self):
        _, trip = self.start()
        self.stop(trip)
        with patch.object(self.processor, "process_trip", side_effect=ProcessingError("transit_context", "secret must not leak")):
            self.api.process_pending()
        _, failed = self.request("GET", f"/trips/{trip['trip_id']}")
        self.assertEqual((failed["status"], failed["failed_step"]), ("failed", "transit_context"))
        self.assertNotIn("secret", failed["error_message"])
        self.stop(trip)
        self.assertEqual(self.api.process_pending(), 0)
        self.stop(trip, {"retry": True, "retry_request_id": "retry-1"})
        self.api.process_pending()
        self.stop(trip, {"retry": True, "retry_request_id": "retry-1"})
        self.assertEqual(self.api.process_pending(), 0)

    def test_authorization_body_cannot_choose_owner(self):
        self.assertEqual(self.request("POST", "/trips/start", token="")[0], 401)
        self.assertEqual(self.request("POST", "/trips/start", {"request_id": "1", "device_id": "d", "user_id": "bob"})[0], 403)
        _, trip = self.start()
        status, _ = dispatch("GET", f"/api/trips/{trip['trip_id']}", {}, b"", self.api, lambda _: "bob")
        self.assertIn(status, (403, 404))
        with patch.dict(os.environ, {"WEBSITE_HOSTNAME": "example.azurewebsites.net"}):
            self.assertEqual(self.start()[0], 503)

    def test_invalid_request_and_idempotency_conflict(self):
        self.assertEqual(self.request("POST", "/trips/start", {"device_id": "d"})[0], 400)
        self.start()
        self.assertEqual(self.request("POST", "/trips/start", {"request_id": "start-001", "device_id": "other"})[0], 409)
        _, trip = self.start()
        self.assertEqual(self.stop(trip, {"ended_at": "yesterday"})[0], 400)

    def test_short_mock_and_bad_processor_output(self):
        _, trip = self.start()
        self.now += timedelta(seconds=30)
        self.request("POST", f"/trips/{trip['trip_id']}/stop")
        self.api.process_pending()
        self.assertEqual(len(self.api.get(trip["trip_id"], "alice")["segments"]), 1)
        _, other = self.start("start-002")
        self.stop(other)
        with patch.object(self.processor, "process_trip", return_value={"trip_id": "wrong", "model_version": "real_v1", "segments": []}):
            self.api.process_pending()
        self.assertEqual(self.api.get(other["trip_id"], "alice")["failed_step"], "validate_segments")

    def test_expired_worker_is_fenced_and_job_recovers(self):
        _, trip = self.start()
        self.stop(trip)
        entered, release = threading.Event(), threading.Event()
        original = self.processor.process_trip
        calls = []

        def slow(item):
            calls.append(item["worker_id"])
            if len(calls) == 1:
                entered.set()
                release.wait(5)
            return original(item)

        with patch.object(self.processor, "process_trip", side_effect=slow):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.api.process_pending)
                self.assertTrue(entered.wait(3))
                self.now += timedelta(seconds=901)
                self.assertEqual(self.api.process_pending(), 1)
                release.set()
                self.assertEqual(first.result(), 0)
        self.assertEqual(self.api.get(trip["trip_id"], "alice")["status"], "ready")

    def test_function_routes_and_worker_registered(self):
        import azure.functions as func
        app = func.FunctionApp()
        app.register_functions(bp)
        self.assertEqual({f.get_function_name() for f in app.get_functions()},
                         {"trip_start", "trip_stop", "trip_get", "trip_worker"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

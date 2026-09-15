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
from services.trip_service import ApiError, TripService
from services.runtime import authenticate
from trip_routes import dispatch, bp

TOKEN = "local-test-token-" + "x" * 32


class TripTests(unittest.TestCase):
    def test_expiring_test_auth_requires_test_environment_and_never_trusts_user_input(self):
        import hashlib, time
        secret = "x" * 48
        credentials = {"device-test": {"sha256": hashlib.sha256(secret.encode()).hexdigest(), "expires_at": time.time()+60}}
        with patch.dict(os.environ, {"APP_ENV":"test", "WEBSITE_HOSTNAME":"azure-test", "TRIP_AUTH_MODE":"test", "TRIP_TEST_CREDENTIALS":json.dumps(credentials)}):
            self.assertEqual(authenticate({"authorization":"Bearer "+secret}), "device-test")
            with self.assertRaises(ApiError) as denied: authenticate({"authorization":"Bearer "+"y"*48})
            self.assertEqual(denied.exception.status, 401)
            with patch.dict(os.environ, {"APP_ENV":"production"}):
                with self.assertRaises(ApiError): authenticate({"authorization":"Bearer "+secret})
            credentials["device-test"]["expires_at"] = time.time()-1
            with patch.dict(os.environ, {"TRIP_TEST_CREDENTIALS":json.dumps(credentials)}):
                with self.assertRaises(ApiError): authenticate({"authorization":"Bearer "+secret})

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
                         {"trip_start", "trip_stop", "trip_get", "trip_confirm", "trip_feedback", "trip_worker"})

    def fixture(self):
        from services.mock_trip_processor import ConfirmationFixtureProcessor
        self.api.processor = ConfirmationFixtureProcessor()
        _, trip = self.start()
        self.stop(trip)
        self.api.process_pending()
        trip = self.api.get(trip["trip_id"], "alice")
        # Legacy pre-feedback record: keep testing correction data compatibility.
        for key in ('carbon','confirmed_trip','revision','confirmed_at','confirmation_source'):
            trip.pop(key, None)
        trip['carbon'] = None
        trip['confirmation_status'] = 'pending'
        trip = self.store.replace(trip)
        body = {"request_id": "confirm-1", "expected_revision": 0,
                "segments": [{"segment_id": s["segment_id"], "confirmed_mode": s["mode"]} for s in trip["segments"]]}
        return trip, body

    def test_stop_immediately_processes_without_waiting_for_timer(self):
        from unittest.mock import Mock
        processor = Mock(wraps=self.processor)
        self.api = TripService(self.store, processor, lambda: self.now, grace_seconds=300, process_on_stop=True)
        _, trip = self.start()
        status, result = self.stop(trip)
        self.assertEqual((status, result["status"]), (200, "ready"))
        self.assertEqual(processor.process_trip.call_count, 1)
        self.stop(trip)
        self.api.process_pending()
        self.assertEqual(processor.process_trip.call_count, 1)

    def test_immediate_stop_does_not_take_over_an_active_worker(self):
        from unittest.mock import Mock
        processor = Mock(wraps=self.processor)
        _, trip = self.start()
        self.stop(trip)
        saved = self.api.get(trip["trip_id"], "alice")
        saved["lease_until"] = (self.now + timedelta(seconds=60)).isoformat()
        self.store.replace(saved)
        self.api = TripService(self.store, processor, lambda: self.now, process_on_stop=True)
        result = self.api.stop(trip["trip_id"], "alice", {})
        self.assertEqual(result["status"], "processing")
        processor.process_trip.assert_not_called()
        self.now += timedelta(seconds=61)
        self.assertEqual(self.api.stop(trip["trip_id"], "alice", {})["status"], "ready")
        self.assertEqual(processor.process_trip.call_count, 1)

    def test_confirmation_preserves_prediction_recalculates_and_survives_restart(self):
        trip, body = self.fixture()
        body["segments"][1]["confirmed_mode"] = "car"
        status, result = self.request("POST", f"/trips/{trip['trip_id']}/confirm", body)
        self.assertEqual(status, 200)
        self.assertEqual(result["original_segments"][1]["mode"], "bus")
        self.assertEqual(result["confirmed_segments"][1]["mode"], "car")
        self.assertEqual(result["segments"][1]["model_prediction"], "bus")
        summary = result["confirmed_trip"]
        self.assertEqual((summary["walk_distance_m"], summary["car_distance_m"], summary["bus_distance_m"]), (800, 6200, 0))
        self.assertEqual(summary["total_distance_m"], 7000)
        self.assertEqual(summary["total_carbon_kg"], 1.028642)
        self.assertEqual(result["carbon"]["kg_co2e"], .778224)
        self.assertEqual(result["confirmed_segments"][1]["carbon_kg"], 1.028642)
        restarted = TripService(SQLiteTripStore(self.path), self.processor)
        self.assertEqual(restarted.get(trip["trip_id"], "alice")["confirmed_trip"], summary)
        body.update(request_id="confirm-2", expected_revision=1)
        body["segments"][1]["confirmed_mode"] = "rail"
        _, updated = self.request("POST", f"/trips/{trip['trip_id']}/confirm", body)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["confirmed_trip"]["total_carbon_kg"], .096038)
        self.assertEqual(updated["original_segments"], result["original_segments"])
        self.assertEqual(len(self.api.get(trip["trip_id"], "alice")["confirmation_history"]), 2)

    def test_confirmation_concurrent_retries_and_stale_revision(self):
        trip, body = self.fixture()
        path = f"/trips/{trip['trip_id']}/confirm"
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.request("POST", path, body), range(6)))
        self.assertTrue(all(status == 200 and result["revision"] == 1 for status, result in results))
        self.assertEqual(self.request("POST", path, {**body, "request_id": "stale"})[0], 409)
        self.assertEqual(self.request("POST", path, {**body, "expected_revision": 1})[0], 409)
        second = {**body, "request_id": "next", "expected_revision": 1}
        self.assertEqual(self.request("POST", path, second)[1]["revision"], 2)
        self.assertEqual(self.request("POST", path, body)[1]["revision"], 2)

    def test_confirmation_rejects_wrong_owner_mode_ids_and_client_distance(self):
        from copy import deepcopy
        trip, body = self.fixture()
        path = f"/trips/{trip['trip_id']}/confirm"
        self.assertEqual(self.request("POST", path, body, token="")[0], 401)
        with self.assertRaises(ApiError): self.api.confirm(trip["trip_id"], "bob", body)
        for change in ({"confirmed_mode": "plane"}, {"distance_m": 0}, {"segment_id": "unknown"}, {"confirmed_mode": []}):
            invalid = deepcopy(body)
            invalid["segments"][0].update(change)
            self.assertEqual(self.request("POST", path, invalid)[0], 400)
        invalid = deepcopy(body)
        invalid["segments"] = invalid["segments"][:1]
        self.assertEqual(self.request("POST", path, invalid)[0], 400)
        self.assertEqual(self.api.get(trip["trip_id"], "alice")["confirmation_status"], "pending")

    def test_carbon_failure_does_not_partially_confirm(self):
        trip, body = self.fixture()
        with patch("services.trip_confirmation.carbon_for", side_effect=RuntimeError("unavailable")):
            self.assertEqual(self.request("POST", f"/trips/{trip['trip_id']}/confirm", body)[0], 503)
        saved = self.api.get(trip["trip_id"], "alice")
        self.assertEqual(saved["confirmation_status"], "pending")
        self.assertNotIn("confirmed_trip", saved)

    def test_stop_preserves_expected_sequence_for_capture_lag(self):
        _, trip = self.start()
        self.stop(trip, {"expected_last_sequence": 211})
        self.assertEqual(self.api.get(trip["trip_id"], "alice")["expected_last_sequence"], 211)
        self.stop(trip, {"expected_last_sequence": 999})
        self.assertEqual(self.api.get(trip["trip_id"], "alice")["expected_last_sequence"], 211)

    def test_trip_database_does_not_reuse_or_change_smoke_database(self):
        from services.runtime import service
        service.cache_clear()
        self.addCleanup(service.cache_clear)
        with patch.dict(os.environ, {"TRIP_STORE": "cosmos", "COSMOS_ENDPOINT": "https://cosmos.test",
                                    "COSMOS_DATABASE": "canopy-smoke", "COSMOS_TRIPS_DATABASE": "canopy-db",
                                    "COSMOS_TRIPS_CONTAINER": "trips", "TRIP_CAMPAIGN_ID": "test-campaign"}):
            with patch("services.runtime.CosmosTripStore") as store:
                service()
                store.assert_called_once_with("https://cosmos.test", "canopy-db", "trips")
                self.assertEqual(os.environ["COSMOS_DATABASE"], "canopy-smoke")
    def test_jwt_signature_expiry_and_audience_are_checked(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from types import SimpleNamespace
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"iss": "https://issuer.test", "aud": "canopy", "sub": "alice",
                  "exp": int(datetime.now(timezone.utc).timestamp()) + 600}
        with patch.dict(os.environ, {"TRIP_AUTH_MODE": "jwt", "TRIP_JWT_ISSUER": claims["iss"],
                                    "TRIP_JWT_AUDIENCE": "canopy", "TRIP_JWKS_URL": "https://issuer.test/keys"}):
            with patch("services.runtime.jwt_keys") as keys:
                keys.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private.public_key())
                valid = jwt.encode(claims, private, algorithm="RS256")
                self.assertEqual(authenticate({"authorization": "Bearer " + valid}), "alice")
                for wrong in ({**claims, "aud": "other"}, {**claims, "exp": 0}):
                    invalid = jwt.encode(wrong, private, algorithm="RS256")
                    self.assertEqual(self.request("GET", "/trips/missing", token=invalid)[0], 401)

    def test_cosmos_adapter_uses_team_partition_and_etag_without_creating_resources(self):
        from unittest.mock import MagicMock
        from azure.core import MatchConditions
        from azure.cosmos.exceptions import CosmosHttpResponseError
        from services.cosmos_service import CosmosTripStore, Conflict
        container = MagicMock()
        container.read.return_value = {"partitionKey": {"paths": ["/user_id"]}}
        with patch("azure.cosmos.CosmosClient") as client, patch("azure.identity.DefaultAzureCredential"):
            client.return_value.get_database_client.return_value.get_container_client.return_value = container
            store = CosmosTripStore("https://cosmos.test", "canopy-db", "trips")
            store.read("trip-1", "alice")
            container.read_item.assert_called_once_with("trip-1", partition_key="alice")
            item = {"id": "trip-1", "trip_id": "trip-1", "user_id": "alice", "_etag": "v1"}
            store.replace(item)
            container.replace_item.assert_called_once_with("trip-1", item, etag="v1", match_condition=MatchConditions.IfNotModified)
            container.replace_item.side_effect = CosmosHttpResponseError(status_code=412)
            with self.assertRaises(Conflict):
                store.replace(item)
            container.read.return_value = {"partitionKey": {"paths": ["/pk"]}}
            with self.assertRaises(ValueError):
                CosmosTripStore("https://cosmos.test", "canopy-db", "trips")


if __name__ == "__main__":
    unittest.main(verbosity=2)

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from services.cosmos_service import SQLiteTripStore
from services.trip_service import TripService
from services.hgb_sandbox import BACKEND, MODEL_SHA256, advance, route_gps


class Publisher:
    def publish(self, event):
        self.event = event


class Processor:
    def process_trip(self, trip):
        raise AssertionError("Production processor must not process HGB trips")


class Job:
    calls = 0
    output = None
    def submit(self, event):
        self.calls += 1
        return 42
    def result(self, run_id):
        assert run_id == 42
        return self.output


class HgbAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteTripStore(self.tmp.name + "/trips.db")
        self.now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        self.publisher = Publisher()
        self.service = TripService(self.store, Processor(), clock=lambda: self.now,
            lifecycle_publisher=self.publisher, result_owner="databricks")
        self.env = patch.dict(os.environ, CANOPY_HGB_APP_ENABLED="true", TRIP_END_EVENTS_ENABLED="true")
        self.env.start(); self.addCleanup(self.env.stop)

    def trip(self):
        t, _ = self.service.start("user", {"request_id":"request", "device_id":"phone"})
        self.now += timedelta(minutes=3)
        with patch("services.hgb_sandbox.advance", side_effect=lambda store, trip:trip):
            return self.service.stop(t["trip_id"], "user", {"expected_last_sequence":181})

    def result(self, t):
        return {"trip_id":t["trip_id"], "user_id":"user", "processing_generation":1,
            "model_sha256":MODEL_SHA256, "is_sandbox":True, "status":"READY",
            "model_version":"hgb_canonical_raw120", "data_quality":{"status":"complete"},
            "segments":[{"segment_id":"one","mode":"walk","start_time":t["started_at"],
                "end_time":t["ended_at"],"distance_m":150,"confidence":0.9}]}

    def test_routing_pinned_and_production_worker_excluded(self):
        t = self.trip()
        self.assertEqual(t["processing_backend"], BACKEND)
        self.assertEqual(t["result_owner"], "functions")
        self.assertEqual(self.publisher.event["processing_backend"], BACKEND)
        self.assertEqual(self.store.pending(self.now.isoformat()), [])
        self.assertEqual(self.store.pending_trip_dispatch(), [])
        self.assertEqual(len(self.store.pending_hgb()), 1)
        with patch.dict(os.environ, CANOPY_HGB_APP_ENABLED="false"):
            again, created = self.service.start("user", {"request_id":"request", "device_id":"phone"})
            self.assertFalse(created); self.assertEqual(again["processing_backend"],BACKEND)
            normal, _ = self.service.start("user", {"request_id":"next", "device_id":"phone"})
            self.assertNotIn("processing_backend", normal)

    def test_stop_submit_poll_publish_and_carbon(self):
        t = self.trip(); job = Job()
        t = advance(self.store,t,job,self.now)
        self.assertEqual(job.calls,1)
        job.output=self.result(t)
        t = advance(self.store,t,job,self.now+timedelta(seconds=31))
        self.assertEqual(t["status"],"ready")
        self.assertEqual(t["carbon"]["kg_co2e"],0)
        self.assertEqual(t["segments"][0]["model_prediction"],"walk")
        self.assertEqual(t["confirmed_trip"]["total_distance_m"],150)
        advance(self.store,t,job,self.now+timedelta(minutes=1))
        self.assertEqual(job.calls,1)

    def test_unpublished_outbox_does_not_dispatch(self):
        t=self.trip();t["trip_end_outbox"]["status"]="pending";job=Job()
        advance(self.store,t,job,self.now)
        self.assertEqual(job.calls,0)

    def test_wrong_generation_rejected(self):
        t=self.trip();job=Job();t=advance(self.store,t,job,self.now)
        job.output=self.result(t);job.output["processing_generation"]=2
        t=advance(self.store,t,job,self.now+timedelta(seconds=31))
        self.assertEqual(t["status"],"failed")
        self.assertEqual(t["failed_step"],"hgb_result_identity")

    def test_stale_worker_cannot_replace_new_generation(self):
        t=self.trip();job=Job();t=advance(self.store,t,job,self.now)
        latest=copy.deepcopy(t);latest["processing_generation"]=2;self.store.replace(latest)
        job.output=self.result(t)
        actual=advance(self.store,t,job,self.now+timedelta(seconds=31))
        self.assertEqual(actual["processing_generation"],2)
        self.assertEqual(actual["status"],"processing")

    def test_gps_goes_to_saved_route_after_switch_off(self):
        t,_=self.service.start("user",{"request_id":"gps","device_id":"phone"})
        with patch.dict(os.environ,CANOPY_HGB_APP_ENABLED="false"), \
             patch("services.runtime.authenticate",return_value="user"), \
             patch("services.runtime.service",return_value=self.service), \
             patch("services.hgb_sandbox.publish") as send:
            self.assertTrue(route_gps({"trip_id":t["trip_id"],"user_id":"user"},{"authorization":"Bearer token"}))
            send.assert_called_once()

if __name__ == "__main__":unittest.main()

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from services.cosmos_service import SQLiteTripStore
from services.trip_service import TripService, ApiError
from services.mock_trip_processor import ConfirmationFixtureProcessor


class Publisher:
    def __init__(self):
        self.events = []
        self.fail = False

    def publish(self, event):
        self.events.append(json.loads(json.dumps(event)))
        if self.fail:
            raise ConnectionError("response lost")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "trips.sqlite")
        self.store = SQLiteTripStore(self.path)
        self.publisher = Publisher()
        self.now = datetime(2026, 9, 16, tzinfo=timezone.utc)
        self.api = TripService(self.store, ConfirmationFixtureProcessor(), lambda: self.now,
                               grace_seconds=0, process_on_stop=True, lifecycle_publisher=self.publisher)

    def start(self, user):
        return self.api.start(user, {"request_id": "start", "device_id": user + "-phone"})[0]

    def stop(self, trip, expected=100):
        self.now += timedelta(seconds=10)
        return self.api.stop(trip["trip_id"], trip["user_id"], {"expected_last_sequence": expected})

    def test_mock_and_event_preserve_identity_and_boundary(self):
        trip = self.start("A")
        ready = self.stop(trip)
        event = self.publisher.events[0]
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["carbon"]["kg_co2e"], .778224)
        for key in ("trip_id", "user_id", "campaign_id", "started_at", "ended_at"):
            self.assertEqual(event[key], ready[key])
        self.assertEqual(event["expected_last_sequence"], 100)
        self.assertEqual(event["event_type"], "trip_ended")
        self.assertEqual(event["result_owner"], "functions")

    def test_duplicate_stop_does_not_change_boundary_or_event_id(self):
        trip = self.start("A")
        first = self.stop(trip)
        second = self.stop(trip, 999)
        self.assertEqual(first["trip_end_outbox"], second["trip_end_outbox"])
        self.assertEqual(len(self.publisher.events), 1)

    def test_lost_ack_survives_ready_and_restart_then_same_id_is_retried(self):
        trip = self.start("A")
        self.publisher.fail = True
        ready = self.stop(trip)
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["trip_end_outbox"]["status"], "pending")
        self.publisher.fail = False
        restarted = TripService(SQLiteTripStore(self.path), ConfirmationFixtureProcessor(),
                                lambda: self.now, lifecycle_publisher=self.publisher)
        restarted.process_pending()
        saved = restarted.get(trip["trip_id"], "A")
        self.assertEqual(saved["trip_end_outbox"]["status"], "published")
        self.assertEqual(self.publisher.events[0], self.publisher.events[1])

    def test_only_stopped_user_emits_event(self):
        trips = [self.start(user) for user in ("A", "B", "C")]
        self.stop(trips[0])
        self.assertEqual([e["user_id"] for e in self.publisher.events], ["A"])
        for trip in trips[1:]:
            self.assertEqual(self.api.get(trip["trip_id"], trip["user_id"])["status"], "collecting")

    def test_databricks_owner_never_runs_mock_or_timer_carbon(self):
        self.api.result_owner = "databricks"
        trip = self.start("A")
        result = self.stop(trip)
        self.api.process_pending()
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["segments"], [])
        self.assertIsNone(result["carbon"])
        self.assertEqual(len(self.publisher.events), 1)

    def test_missing_or_invalid_boundary_does_not_stop_trip(self):
        trip = self.start("A")
        for body in ({}, {"expected_last_sequence": True}, {"expected_last_sequence": -1}):
            with self.assertRaises(ApiError):
                self.api.stop(trip["trip_id"], "A", body)
        self.assertEqual(self.api.get(trip["trip_id"], "A")["status"], "collecting")
        self.assertEqual(self.publisher.events, [])

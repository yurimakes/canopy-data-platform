import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from services.cosmos_service import SQLiteTripStore
from services.trip_service import TripService
from services.mock_trip_processor import MockTripProcessor
from services.trip_dispatch import receive, recover


class Publisher:
    def publish(self, event):
        pass


class Job:
    def __init__(self):
        self.sent = []
        self.failure = False
        self.finished = False

    def submit(self, event):
        self.sent.append(event["event_id"])
        if self.failure:
            raise ConnectionError()
        return 123

    def state(self, run_id):
        return {"life_cycle_state": "TERMINATED", "result_state": "FAILED"} if self.finished else {"life_cycle_state": "RUNNING"}


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteTripStore(str(Path(self.temp.name) / "db"))
        self.now = datetime(2026, 9, 16, 0, tzinfo=timezone.utc)
        self.service = TripService(self.store, MockTripProcessor(), clock=lambda: self.now,
                                   lifecycle_publisher=Publisher(), result_owner="databricks")
        trip, _ = self.service.start("user", {"request_id": "request", "device_id": "phone"})
        self.now += timedelta(seconds=10)
        self.trip = self.service.stop(trip["trip_id"], "user", {"expected_last_sequence": 2})
        self.event = self.trip["trip_end_outbox"]["event"]

    def current(self):
        return self.store.read(self.trip["trip_id"], "user")

    def test_published_outbox_recovers_missing_receipt_once(self):
        job = Job()
        recover(self.store, job, self.now)
        self.assertEqual(job.sent, [self.event["event_id"]])
        self.assertFalse(receive(self.store, {**self.event, "expected_last_sequence": 3}, self.now))
        self.assertFalse(receive(self.store, {"event_type": "gps"}, self.now))
        self.assertTrue(receive(self.store, self.event, self.now))
        recover(self.store, job, self.now)
        receive(self.store, self.event, self.now)
        recover(self.store, job, self.now + timedelta(seconds=61))
        self.assertEqual(job.sent, [self.event["event_id"]])
        self.assertEqual(self.current()["trip_dispatch"]["run_id"], 123)

    def test_unpublished_outbox_does_not_launch(self):
        trip = self.current()
        trip["trip_end_outbox"]["status"] = "pending"
        self.store.replace(trip)
        job = Job()
        recover(self.store, job, self.now)
        self.assertEqual(job.sent, [])

    def test_lost_submission_retries_same_id_after_restart(self):
        job = Job(); job.failure = True
        receive(self.store, self.event, self.now)
        recover(self.store, job, self.now)
        job.failure = False
        store = SQLiteTripStore(self.store.path)
        recover(store, job, self.now + timedelta(seconds=61))
        self.assertEqual(job.sent, [self.event["event_id"]] * 2)

    def test_missing_receipt_and_failed_job_have_bounded_failure(self):
        recover(self.store, Job(), self.now + timedelta(seconds=1801))
        self.assertEqual(self.current()["status"], "failed")
        self.assertEqual(self.current()["failed_step"], "databricks_timeout")

    def test_job_failure_is_visible_without_waiting_forever(self):
        job = Job()
        receive(self.store, self.event, self.now)
        recover(self.store, job, self.now)
        job.finished = True
        recover(self.store, job, self.now + timedelta(seconds=61))
        self.assertEqual(self.current()["failed_step"], "databricks_job_failed")

    def test_old_run_cannot_fail_new_generation(self):
        job = Job()
        receive(self.store, self.event, self.now)
        recover(self.store, job, self.now)
        current = self.current(); current["status"] = "failed"; self.store.replace(current)
        self.service.stop(current["trip_id"], "user", {"retry": True, "retry_request_id": "r2"})
        job.finished = True
        recover(self.store, job, self.now + timedelta(seconds=61))
        self.assertEqual(self.current()["status"], "processing")


if __name__ == "__main__":
    unittest.main()

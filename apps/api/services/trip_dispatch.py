"""Event Hubs receipt -> existing Databricks Job, with durable retry and watchdog."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from .cosmos_service import Conflict


@lru_cache
def credential():
    from azure.identity import DefaultAzureCredential
    return DefaultAzureCredential()


class DatabricksJob:
    def call(self, path, body=None):
        import requests
        token = credential().get_token("2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default").token
        host = os.environ["TRIP_DATABRICKS_HOST"].rstrip("/")
        response = requests.request("POST" if body is not None else "GET", host + path,
                                    json=body, headers={"Authorization": "Bearer " + token}, timeout=10)
        if not response.ok:
            raise RuntimeError("Databricks HTTP " + str(response.status_code))
        return response.json()

    def submit(self, event):
        return self.call("/api/2.1/jobs/run-now", {"job_id": int(os.environ["TRIP_DATABRICKS_JOB_ID"]),
            "idempotency_token": event["event_id"], "job_parameters": {"end_event": json.dumps(event),
            "input_mode": os.getenv("TRIP_DATABRICKS_INPUT", "ml")}})["run_id"]

    def state(self, run_id):
        return self.call("/api/2.1/jobs/runs/get?run_id=" + str(int(run_id))).get("state", {})


def receive(store, event, now=None):
    if event.get("event_type") != "trip_ended":
        return False
    now = now or datetime.now(timezone.utc)
    for _ in range(5):
        trip = store.read(event.get("trip_id", ""), event.get("user_id", ""))
        if not trip or trip.get("result_owner") != "databricks" or trip.get("status") != "processing":
            return False
        if trip.get("trip_end_outbox", {}).get("event") != event:
            return False  # Never launch from an event that differs from the authenticated Stop.
        dispatch = trip.get("trip_dispatch", {})
        if dispatch.get("event_id") == event["event_id"]:
            return True
        trip["trip_dispatch"] = {"event_id": event["event_id"], "received_at": now.isoformat(),
                                 "next_attempt_at": now.isoformat(), "attempts": 0}
        try:
            store.replace(trip)
            return True
        except Conflict:
            continue
    raise RuntimeError("End receipt storage conflicted; retry the event")


def recover(store, api=None, now=None):
    api = api or DatabricksJob()
    now = now or datetime.now(timezone.utc)
    for candidate in store.pending_trip_dispatch():
        trip = store.read(candidate["trip_id"], candidate["user_id"])
        dispatch = trip.get("trip_dispatch", {})
        if trip["status"] != "processing" or trip.get("result_owner") != "databricks":
            continue
        if dispatch.get("next_attempt_at", "") > now.isoformat():
            continue
        event = trip.get("trip_end_outbox", {}).get("event", {})
        failure = None
        try:
            # Bounds failures before/after Job startup too, not only ML waiting inside Spark.
            if now >= datetime.fromisoformat(trip["ended_at"]) + timedelta(seconds=1800):
                failure = "databricks_timeout"
            elif not dispatch or dispatch.get("event_id") != event.get("event_id"):
                continue  # The Event Hubs trigger must first record the actual receipt.
            elif dispatch.get("run_id") is None:
                dispatch = {**dispatch, "run_id": api.submit(event)}
            else:
                state = api.state(dispatch["run_id"])
                if state.get("life_cycle_state") in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                    # A successful runner has already written ready/failed to Cosmos.
                    latest = store.read(trip["trip_id"], trip["user_id"])
                    if latest["status"] != "processing":
                        continue
                    failure = "databricks_result_missing" if state.get("result_state") == "SUCCESS" else "databricks_job_failed"
        except Exception as exc:
            logging.warning("trip_dispatch_retry trip_id=%s error_type=%s", trip["trip_id"], type(exc).__name__)
        latest = store.read(trip["trip_id"], trip["user_id"])
        if latest["status"] != "processing" or latest["processing_generation"] != trip["processing_generation"]:
            continue
        dispatch.update(next_attempt_at=(now + timedelta(seconds=60)).isoformat(),
                        attempts=dispatch.get("attempts", 0) + 1)
        latest["trip_dispatch"] = dispatch
        if failure:
            latest.update(status="failed", failed_step=failure,
                          error_message="Processing did not finish. Please retry.")
        try:
            store.replace(latest)
        except Conflict:
            pass  # The next timer invocation resumes from durable state.

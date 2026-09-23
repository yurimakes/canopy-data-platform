"""Reversible routing of new app trips to the isolated HGB job."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from .cosmos_service import Conflict
from .trip_dispatch import DatabricksJob
from .trip_processor import ProcessingError, timestamp, validate_result

BACKEND = "hgb_sandbox_5dt024"
HUB = "evh-canopy-sandbox-5dt024"
JOB_ID = 1025081607321226
MODEL_SHA256 = "f1c30c2923bccdb9018dd9d722167a1e7902450ec47ca8408bacfd300e533878"
LOG = logging.getLogger(__name__)


def selected(trip):
    return trip.get("processing_backend") == BACKEND


def route_new_trip(trip):
    # Freeze routing at Start: changing the switch cannot split an active trip.
    if os.getenv("CANOPY_HGB_APP_ENABLED", "false").lower() == "true":
        if os.getenv("TRIP_END_EVENTS_ENABLED", "false").lower() != "true":
            raise RuntimeError("HGB app routing requires lifecycle publishing")
        trip.update(processing_backend=BACKEND, result_owner="functions")


def route_gps(payload, headers):
    """Return True only after an authenticated sandbox GPS send has succeeded."""
    from .runtime import authenticate, service
    from .trip_service import ApiError
    if not isinstance(payload, dict):
        return False
    # Existing production GPS requests keep their original output binding.
    # Authenticated requests use the server-stored trip route, never a body flag.
    authorization = headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        if os.getenv("CANOPY_HGB_APP_ENABLED", "false").lower() == "true":
            raise ApiError(401, "unauthorized", "login required")
        return False
    user_id = authenticate(headers)
    trip = service().get(payload.get("trip_id", ""), user_id)
    if not selected(trip):
        return False
    if payload.get("user_id") != user_id:
        raise ApiError(403, "forbidden", "GPS user differs from authenticated user")
    if trip["status"] != "collecting":
        raise ApiError(409, "trip_closed", "GPS upload must finish before Trip stop")
    publish(payload)
    return True


def publish(event):
    from azure.eventhub import EventData, EventHubProducerClient
    from .trip_dispatch import credential
    with EventHubProducerClient(fully_qualified_namespace=os.environ["EVENTHUB_FQDN"],
            eventhub_name=HUB, credential=credential(), retry_total=2,
            auth_timeout=5, socket_timeout=5) as producer:
        batch = producer.create_batch(partition_key=event["trip_id"])
        batch.add(EventData(json.dumps(event, ensure_ascii=False, allow_nan=False)))
        producer.send_batch(batch, timeout=10)


class HgbJob(DatabricksJob):
    def submit(self, event):
        return self.call("/api/2.1/jobs/run-now", {
            "job_id": JOB_ID, "idempotency_token": event["event_id"],
            "job_parameters": {"trip_id": event["trip_id"], "user_id": event["user_id"],
                "processing_generation": str(event["processing_generation"])}})["run_id"]

    def result(self, run_id):
        run = self.call("/api/2.1/jobs/runs/get?run_id=" + str(int(run_id)))
        if run.get("job_id") != JOB_ID:
            raise ValueError("Unexpected HGB job identity")
        state = run.get("state", {})
        if state.get("life_cycle_state") not in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
            return None
        if state.get("result_state") != "SUCCESS":
            raise ProcessingError("hgb_job_failed", "HGB job did not succeed")
        task = next(t for t in run["tasks"] if t["task_key"] == "hgb_trip")
        output = self.call("/api/2.1/jobs/runs/get-output?run_id=" + str(int(task["run_id"])))
        notebook = output.get("notebook_output", {})
        if notebook.get("truncated") or not notebook.get("result"):
            raise ProcessingError("hgb_result_missing", "No complete HGB result")
        return json.loads(notebook["result"])


def apply_result(trip, result, now):
    if (result.get("user_id") != trip["user_id"]
            or result.get("processing_generation") != trip["processing_generation"]
            or result.get("model_sha256") != MODEL_SHA256
            or result.get("is_sandbox") is not True):
        raise ProcessingError("hgb_result_identity", "HGB result identity differs")
    if result.get("status") != "READY" or not result.get("segments"):
        raise ProcessingError("hgb_insufficient_gps", "No complete 120-second GPS window")
    validate_result(trip, result)
    segments = [{**s, "model_prediction": s["mode"], "confirmed_mode": None,
        "corrected": False, "correction_status": "none", "confirmation_time": None,
        "last_request_id": None, "started_at": s["start_time"], "ended_at": s["end_time"],
        "duration_min": (timestamp(s["end_time"]) - timestamp(s["start_time"])).total_seconds()/60}
        for s in result["segments"]]
    trip.update(segments=segments, model_version=result["model_version"], is_mock=False,
        status="ready", data_quality=result.get("data_quality"), model_sha256=MODEL_SHA256,
        failed_step=None, error_message=None)
    from .trip_carbon import finalize_result
    finalize_result(trip, segments, now.isoformat())


def advance(store, trip, api=None, now=None):
    if not selected(trip) or trip.get("status") != "processing":
        return trip
    api = api or HgbJob()
    now = now or datetime.now(timezone.utc)
    event = trip.get("trip_end_outbox", {}).get("event", {})
    if trip.get("trip_end_outbox", {}).get("status") != "published":
        return trip
    dispatch = trip.get("hgb_dispatch", {})
    if dispatch.get("event_id") != event.get("event_id"):
        dispatch = {"event_id": event["event_id"], "attempts": 0, "started_at": now.isoformat()}
    if dispatch.get("next_attempt_at", "") > now.isoformat():
        return trip
    try:
        if now > timestamp(dispatch["started_at"]) + timedelta(minutes=30):
            raise ProcessingError("hgb_timeout", "HGB processing timed out")
        if not dispatch.get("run_id"):
            dispatch["run_id"] = api.submit(event)
        else:
            result = api.result(dispatch["run_id"])
            if result is not None:
                apply_result(trip, result, now)
    except ProcessingError as exc:
        trip.update(status="failed", segments=[], model_version=None,
            failed_step=exc.step, error_message="HGB 분석을 완료하지 못했습니다. GPS 기록을 확인하고 다시 시도해 주세요.")
    except Exception as exc:
        LOG.warning("hgb_retry trip_id=%s error_type=%s", trip["trip_id"], type(exc).__name__)
    dispatch.update(next_attempt_at=(now + timedelta(seconds=30)).isoformat(), attempts=dispatch["attempts"]+1)
    trip.update(hgb_dispatch=dispatch, updated_at=now.isoformat())
    try:
        return store.replace(trip)
    except Conflict:
        # Stable event_id prevents duplicate Jobs; CAS prevents stale generation publication.
        return store.read(trip["trip_id"], trip["user_id"])


def recover(store):
    for trip in store.pending_hgb():
        advance(store, trip)

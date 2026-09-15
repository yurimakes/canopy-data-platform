import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5
from .cosmos_service import Conflict, TripStore
from .trip_processor import TripProcessor, ProcessingError, timestamp, validate_result

LOG = logging.getLogger(__name__)
NAMESPACE = UUID("092b406a-31cb-4fdb-9519-52d32a35794f")


def utcnow():
    return datetime.now(timezone.utc)


def iso(value: datetime):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code = status, code
        super().__init__(message)


def required(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ApiError(400, "invalid_field", key + " must be a nonempty string (max 200)")
    return value


def public(item: dict) -> dict:
    fields = ("trip_id", "user_id", "device_id", "campaign_id", "status", "started_at", "ended_at", "created_at", "updated_at",
              "segments", "model_version", "failed_step", "error_message", "is_mock", "confirmation_status", "carbon",
              "original_segments", "confirmed_segments", "revision", "confirmed_at", "confirmed_trip")
    return {key: item.get(key) for key in fields}


class TripService:
    def confirm(self, trip_id, user_id, body):
        from .trip_confirmation import confirm
        return confirm(self, trip_id, user_id, body)

    def __init__(self, store: TripStore, processor: TripProcessor, clock=utcnow, grace_seconds=5, lease_seconds=900, campaign_id="local-test", process_on_stop=False):
        self.store, self.processor, self.clock = store, processor, clock
        self.campaign_id = campaign_id
        self.grace_seconds, self.lease_seconds = grace_seconds, lease_seconds
        self.process_on_stop = process_on_stop

    def after_stop(self, item):
        if self.process_on_stop and item["status"] == "processing":
            # Start only this Trip, using the same durable claim as the recovery timer.
            if item.get("lease_until", "") <= iso(self.clock()):
                self._process([item])
            return self.get(item["trip_id"], item["user_id"])
        return item

    def get(self, trip_id: str, user_id: str) -> dict:
        item = self.store.read(trip_id, user_id)
        if not item or item.get("type") != "trip":
            raise ApiError(404, "not_found", "trip not found")
        if item["user_id"] != user_id:
            raise ApiError(403, "forbidden", "cannot access another user's trip")
        return item

    def start(self, user_id: str, body: dict) -> tuple[dict, bool]:
        request_id, device_id = required(body, "request_id"), required(body, "device_id")
        if "user_id" in body and body["user_id"] != user_id:
            raise ApiError(403, "forbidden", "user_id differs from authenticated user")
        # Server-issued stable ID: a lost HTTP response cannot create another Trip.
        trip_id = str(uuid5(NAMESPACE, json.dumps([user_id, request_id])))
        fingerprint = hashlib.sha256(device_id.encode()).hexdigest()
        now = iso(self.clock())
        item = {"id": trip_id, "type": "trip", "trip_id": trip_id, "user_id": user_id, "device_id": device_id,
                "campaign_id": self.campaign_id, "planned_route": None,
                "start_request_id": request_id, "start_fingerprint": fingerprint,
                "status": "collecting", "started_at": now, "ended_at": None, "created_at": now, "updated_at": now,
                "segments": [], "model_version": None, "failed_step": None, "error_message": None,
                "is_mock": False, "confirmation_status": "pending", "carbon": None,
                "processing_generation": 0, "lease_until": "", "process_after": "", "last_retry_id": None}
        try:
            item = self.store.create(item)
            LOG.info("trip_started trip_id=%s", trip_id)
            return item, True
        except Conflict:
            item = self.get(trip_id, user_id)
            if item["start_fingerprint"] != fingerprint:
                raise ApiError(409, "idempotency_conflict", "request_id was used with another device_id")
            return item, False

    def stop(self, trip_id: str, user_id: str, body: dict) -> dict:
        retry_id = required(body, "retry_request_id") if body.get("retry") is True else None
        for _ in range(8):
            item = self.get(trip_id, user_id)
            if item["status"] != "collecting":
                if item["status"] != "failed" or not retry_id or item.get("last_retry_id") == retry_id:
                    return self.after_stop(item)
            now = self.clock()
            if item["status"] == "collecting":
                expected = body.get("expected_last_sequence")
                if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int) or not 0 <= expected <= 10000000):
                    raise ApiError(400, "invalid_field", "expected_last_sequence must be a nonnegative integer")
                try:
                    ended = timestamp(body.get("ended_at", iso(now)))
                except (ValueError, TypeError) as exc:
                    raise ApiError(400, "invalid_field", "ended_at must include timezone") from exc
                if ended < timestamp(item["started_at"]) or ended > now + timedelta(minutes=2):
                    raise ApiError(400, "invalid_field", "ended_at is outside the Trip interval")
                item["ended_at"] = iso(ended)
                item["expected_last_sequence"] = expected
            item.update(status="processing", updated_at=iso(now), segments=[], model_version=None,
                        failed_step=None, error_message=None, is_mock=False,
                        process_after=iso(now + timedelta(seconds=self.grace_seconds)), lease_until="",
                        processing_generation=item["processing_generation"] + 1, last_retry_id=retry_id)
            try:
                saved = self.store.replace(item)
                LOG.info("trip_processing trip_id=%s generation=%s", trip_id, saved["processing_generation"])
                return self.after_stop(saved)
            except Conflict:
                continue
        raise ApiError(409, "concurrent_update", "retry the same stop request")

    def process_pending(self, limit=20) -> int:
        return self._process(self.store.pending(iso(self.clock()), limit))

    def _process(self, items) -> int:
        processed = 0
        for item in items:
            item.update(lease_until=iso(self.clock() + timedelta(seconds=self.lease_seconds)), worker_id=str(uuid4()))
            try:
                claimed = self.store.replace(item)
            except Conflict:
                continue
            try:
                result = self.processor.process_trip(claimed)
                validate_result(claimed, result)
                segments = [{**segment, "model_prediction": segment["mode"],
                             "confirmed_mode": None, "corrected": False, "correction_status": "none",
                             "confirmation_time": None, "last_request_id": None,
                             "start_name": segment.get("start_name"), "end_name": segment.get("end_name"),
                             "route_name": segment.get("route_name"),
                             "started_at": segment["start_time"], "ended_at": segment["end_time"],
                             "duration_min": (timestamp(segment["end_time"]) - timestamp(segment["start_time"])).total_seconds() / 60}
                            for segment in result["segments"]]
                claimed.update(segments=segments, model_version=result["model_version"],
                               is_mock=result["model_version"] == "mock_v1", status="ready")
            except Exception as exc:
                step = exc.step if isinstance(exc, ProcessingError) else "process_trip"
                # Do not send exception text containing infrastructure URLs/secrets to phones.
                claimed.update(status="failed", failed_step=step,
                               error_message="Trip processing failed. Retry after checking the processor.")
                LOG.error("trip_failed trip_id=%s step=%s error_type=%s", item["trip_id"], step, type(exc).__name__)
            claimed.update(updated_at=iso(self.clock()), lease_until="")
            try:
                self.store.replace(claimed)
                processed += 1
                LOG.info("trip_result trip_id=%s status=%s", claimed["trip_id"], claimed["status"])
            except Conflict:
                LOG.warning("trip_stale_worker trip_id=%s", item["trip_id"])
        return processed

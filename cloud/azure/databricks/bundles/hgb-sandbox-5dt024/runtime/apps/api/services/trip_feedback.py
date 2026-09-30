"""One immutable user response per Trip. Feedback never changes result fields."""
import hashlib
import json
import logging
from uuid import uuid5
from .cosmos_service import Conflict, CosmosTripStore, SQLiteTripStore
from .trip_service import ApiError, NAMESPACE, iso, required

LOG = logging.getLogger(__name__)
MAX_FEEDBACK_LENGTH = 500


class CosmosFeedbackStore(CosmosTripStore):
    def __init__(self, client, database, container):
        self.client = client
        self.container = client.get_database_client(database).get_container_client(container)
        if self.container.read()["partitionKey"]["paths"] != ["/user_id"]:
            raise ValueError("feedback partition key must match the existing user partition pattern")

    def pending(self, limit=20):
        return list(self.container.query_items(
            query=f"SELECT TOP {int(limit)} * FROM c WHERE c.type='trip_feedback' AND c.trip_flag_applied=false",
            enable_cross_partition_query=True))


class SQLiteFeedbackStore(SQLiteTripStore):
    """Separate local database using the existing durable JSON/CAS adapter."""
    def pending(self, limit=20):
        with self.connect() as db:
            rows = db.execute("SELECT version,payload FROM trips WHERE json_extract(payload,'$.type')='trip_feedback' "
                              "AND json_extract(payload,'$.trip_flag_applied')=0 LIMIT ?", (limit,)).fetchall()
        return [{**json.loads(payload), "_etag": str(version)} for version, payload in rows]


def validate_feedback(body):
    if set(body) - {"request_id", "has_issue", "feedback_text"}:
        raise ApiError(400, "invalid_field", "unexpected feedback field")
    request_id = required(body, "request_id")
    has_issue, text = body.get("has_issue"), body.get("feedback_text")
    if type(has_issue) is not bool:
        raise ApiError(400, "invalid_field", "has_issue must be boolean")
    if text is not None and not isinstance(text, str):
        raise ApiError(400, "invalid_field", "feedback_text must be string or null")
    if text is not None and len(text) > MAX_FEEDBACK_LENGTH:
        raise ApiError(400, "invalid_field", "feedback_text must be at most 500 characters")
    text = (text.strip() or None) if text is not None else None
    if not has_issue and text:
        raise ApiError(400, "invalid_field", "no_issue cannot include feedback text")
    if text and any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise ApiError(400, "invalid_field", "feedback_text must contain valid Unicode")
    fingerprint = hashlib.sha256(json.dumps([has_issue, text], ensure_ascii=False).encode()).hexdigest()
    return request_id, has_issue, text, fingerprint


class TripFeedbackService:
    def __init__(self, trips, store):
        self.trips, self.store = trips, store

    def submit(self, trip_id, user_id, body):
        request_id, has_issue, text, fingerprint = validate_feedback(body)
        LOG.info("feedback_received trip_id=%s", trip_id)
        feedback_id = str(uuid5(NAMESPACE, json.dumps(["feedback", user_id, trip_id])))
        for _ in range(8):
            trip = self.trips.get(trip_id, user_id)
            if trip["status"] != "ready":
                raise ApiError(409, "trip_not_ready", "wait for the Trip result")
            submission = trip.get("feedback_submission")
            if submission:
                if submission["fingerprint"] != fingerprint:
                    raise ApiError(409, "feedback_already_answered", "one feedback response is allowed per Trip")
                if trip.get("feedback_status") in ("submitted", "no_issue"):
                    LOG.info("feedback_duplicate_ignored trip_id=%s feedback_id=%s", trip_id, trip.get("feedback_id"))
                    return trip
                break
            # Reserve the response with CAS so concurrent yes/no cannot contradict
            # each other. No text is copied into trips, and pending is not success.
            submission = {"request_id": request_id, "fingerprint": fingerprint, "has_issue": has_issue,
                          "feedback_id": feedback_id if has_issue else None, "created_at": iso(self.trips.clock())}
            trip.update(feedback_submission=submission, feedback_status="pending" if has_issue else "no_issue",
                        review_required=False, has_issue=None if has_issue else False,
                        feedback_id=None, feedback_updated_at=submission["created_at"])
            try:
                trip = self.trips.store.replace(trip)
                if not has_issue:
                    LOG.info("trip_flag_updated trip_id=%s review_required=false", trip_id)
                    return trip
                break
            except Conflict:
                continue
        else:
            raise ApiError(409, "concurrent_update", "retry the same feedback request")
        document = {"id": feedback_id, "feedback_id": feedback_id, "type": "trip_feedback",
                    "trip_id": trip_id, "user_id": user_id, "has_issue": True, "feedback_text": text,
                    "created_at": submission["created_at"], "review_status": "pending",
                    "request_id": submission["request_id"], "fingerprint": fingerprint, "trip_flag_applied": False}
        try:
            try:
                saved = self.store.create(document)
                LOG.info("feedback_saved trip_id=%s feedback_id=%s", trip_id, feedback_id)
            except Conflict:
                saved = self.store.read(feedback_id, user_id)
                if not saved or saved["fingerprint"] != fingerprint:
                    raise ApiError(409, "feedback_conflict", "feedback identity conflicts with stored response")
                LOG.info("feedback_duplicate_ignored trip_id=%s feedback_id=%s", trip_id, feedback_id)
        except Exception:
            LOG.error("feedback_save_failed trip_id=%s feedback_id=%s", trip_id, feedback_id)
            raise
        return self.apply_flag(saved)

    def apply_flag(self, document):
        trip_id, user_id = document["trip_id"], document["user_id"]
        try:
            for _ in range(8):
                trip = self.trips.get(trip_id, user_id)
                submission = trip.get("feedback_submission") or {}
                if submission.get("fingerprint") != document["fingerprint"] or not submission.get("has_issue"):
                    raise ApiError(409, "feedback_conflict", "Trip response does not match feedback")
                if trip.get("feedback_status") == "submitted":
                    break
                trip.update(review_required=True, has_issue=True, feedback_status="submitted",
                            feedback_id=document["feedback_id"], feedback_updated_at=iso(self.trips.clock()))
                try:
                    trip = self.trips.store.replace(trip)
                    LOG.info("trip_flag_updated trip_id=%s feedback_id=%s", trip_id, document["feedback_id"])
                    break
                except Conflict:
                    continue
            else:
                raise ApiError(409, "concurrent_update", "retry the same feedback request")
            # The feedback document is the repair record if the host dies after
            # its create but before the Trip flag write. Existing timer retries it.
            for _ in range(8):
                current = self.store.read(document["id"], user_id)
                if current["trip_flag_applied"]:
                    return trip
                current["trip_flag_applied"] = True
                try:
                    self.store.replace(current)
                    return trip
                except Conflict:
                    continue
            raise ApiError(409, "concurrent_update", "feedback flag acknowledgement needs retry")
        except Exception:
            LOG.error("trip_flag_update_failed trip_id=%s feedback_id=%s", trip_id, document["feedback_id"])
            raise

    def recover_pending(self, limit=20):
        repaired = 0
        for document in self.store.pending(limit):
            try:
                self.apply_flag(document)
                repaired += 1
            except Exception:
                # No feedback text or infrastructure exception details in logs.
                LOG.error("trip_flag_update_failed trip_id=%s feedback_id=%s", document["trip_id"], document["feedback_id"])
        return repaired

"""Durable Trip end outbox stored atomically with the existing Trip state."""
import json
import logging
import os
from uuid import uuid5, NAMESPACE_URL
from .cosmos_service import Conflict

LOG = logging.getLogger(__name__)


def end_event(trip, occurred_at):
    generation = trip["processing_generation"]
    return {"event_id": str(uuid5(NAMESPACE_URL, json.dumps([trip["user_id"], trip["trip_id"], generation, "trip_ended"]))),
            "event_type": "trip_ended", "schema_version": "trip-lifecycle-v1",
            **{key: trip[key] for key in ("trip_id", "user_id", "campaign_id", "started_at", "ended_at", "expected_last_sequence")},
            "occurred_at": occurred_at, "processing_generation": generation,
            "result_owner": trip["result_owner"]}


class EventHubLifecyclePublisher:
    def publish(self, event):
        from azure.eventhub import EventData, EventHubProducerClient, TransportType
        from azure.identity import DefaultAzureCredential
        with DefaultAzureCredential() as credential:
            with EventHubProducerClient(fully_qualified_namespace=os.environ["EVENTHUB_FQDN"],
                    eventhub_name=os.environ["EVENTHUB_NAME"], credential=credential,
                    transport_type=TransportType.AmqpOverWebsocket, retry_total=0,
                    auth_timeout=5, socket_timeout=5) as producer:
                batch = producer.create_batch(partition_key=event["trip_id"])
                batch.add(EventData(json.dumps(event, ensure_ascii=False, allow_nan=False)))
                producer.send_batch(batch, timeout=5)


def deliver(store, publisher, trip, now):
    outbox = trip.get("trip_end_outbox")
    if not outbox or outbox["status"] == "published":
        return trip
    event = outbox["event"]
    try:
        publisher.publish(event)
    except Exception as exc:
        LOG.error("trip_end_publish_pending event_id=%s trip_id=%s error_type=%s",
                  event["event_id"], event["trip_id"], type(exc).__name__)
        return store.read(trip["trip_id"], trip["user_id"])
    # The send may succeed even if this acknowledgement write fails. Retry the SAME event_id.
    for _ in range(8):
        current = store.read(trip["trip_id"], trip["user_id"])
        current_outbox = current.get("trip_end_outbox", {})
        if current_outbox.get("event", {}).get("event_id") != event["event_id"] or current_outbox.get("status") == "published":
            return current
        current["trip_end_outbox"] = {**current_outbox, "status": "published", "published_at": now}
        try:
            saved = store.replace(current)
            LOG.info("trip_end_published event_id=%s trip_id=%s user_id=%s expected_last_sequence=%s",
                     event["event_id"], event["trip_id"], event["user_id"], event["expected_last_sequence"])
            return saved
        except Conflict:
            continue
    return store.read(trip["trip_id"], trip["user_id"])

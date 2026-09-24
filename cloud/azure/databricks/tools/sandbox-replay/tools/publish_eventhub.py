#!/usr/bin/env python3
"""Replay a committed canonical GPS fixture to Azure Event Hubs."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from azure.eventhub import EventData, EventHubProducerClient
from dotenv import load_dotenv
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")


def ts(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_events(trip: Path, duration: float | None) -> list[dict]:
    events = [
        json.loads(line)
        for line in (trip / "gps_raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not events:
        raise SystemExit("empty fixture")
    if duration is not None:
        start = ts(events[0]["event_time"])
        events = [
            event
            for event in events
            if ts(event["event_time"]) - start <= duration
        ]
    if not events:
        raise SystemExit("duration cutoff selected no GPS events")
    return events


def fresh_identity(events: list[dict]) -> tuple[str, str, str]:
    trip_id, user_id, device_id = str(uuid4()), str(uuid4()), str(uuid4())
    for event in events:
        event["event_id"] = str(uuid4())
        event["trip_id"] = trip_id
        event["user_id"] = user_id
        event["device_id"] = device_id
    return trip_id, user_id, device_id


def trip_end(events: list[dict], campaign: str) -> dict:
    first, last = events[0], events[-1]
    return {
        "event_id": str(uuid4()),
        "event_type": "trip_ended",
        "schema_version": "trip-lifecycle-v1",
        "trip_id": first["trip_id"],
        "user_id": first["user_id"],
        "campaign_id": campaign,
        "started_at": first["event_time"],
        "ended_at": last["event_time"],
        "expected_last_sequence": last["sequence"],
        "occurred_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "processing_generation": 1,
        "result_owner": "databricks",
    }


def send_batch(producer, events: list[dict], partition_key: str) -> None:
    batch = producer.create_batch(partition_key=partition_key)
    for obj in events:
        event = EventData(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        try:
            batch.add(event)
        except ValueError:
            producer.send_batch(batch)
            batch = producer.create_batch(partition_key=partition_key)
            batch.add(event)
    if len(batch):
        producer.send_batch(batch)


def partition_positions(producer) -> dict[str, int]:
    properties = producer.get_eventhub_properties()
    return {
        partition_id: producer.get_partition_properties(partition_id)[
            "last_enqueued_sequence_number"
        ]
        for partition_id in properties["partition_ids"]
    }


def total_appended(before: dict[str, int], after: dict[str, int]) -> int:
    return sum(after[partition_id] - before.get(partition_id, -1) for partition_id in after)


def wait_for_append(
    producer,
    before: dict[str, int],
    expected_count: int,
    timeout_seconds: float,
) -> tuple[dict[str, int], int]:
    deadline = time.monotonic() + timeout_seconds
    after = partition_positions(producer)
    appended = total_appended(before, after)
    while appended < expected_count and time.monotonic() < deadline:
        time.sleep(0.25)
        after = partition_positions(producer)
        appended = total_appended(before, after)
    return after, appended


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--replay-cadence-ms", type=int, default=0)
    parser.add_argument("--no-trip-end", action="store_true")
    parser.add_argument("--campaign-id", default="campaign_test")
    parser.add_argument(
        "--event-hub",
        default=os.getenv("EVENT_HUB_NAME", "evh-canopy-sandbox-5dt016"),
    )
    parser.add_argument(
        "--verify-timeout-seconds",
        type=float,
        default=10.0,
        help="Wait up to this long for Event Hubs partition metadata to reflect the publish.",
    )
    args = parser.parse_args()

    if args.replay_cadence_ms < 0:
        raise SystemExit("--replay-cadence-ms must be >= 0")
    if args.verify_timeout_seconds <= 0:
        raise SystemExit("--verify-timeout-seconds must be > 0")

    connection_string = os.getenv("EVENT_HUB_CONNECTION_STRING")
    if not connection_string:
        raise SystemExit("EVENT_HUB_CONNECTION_STRING is required")

    events = load_events(args.trip, args.duration_seconds)
    trip_id, user_id, device_id = fresh_identity(events)
    lifecycle_event = None if args.no_trip_end else trip_end(events, args.campaign_id)
    expected_publish_count = len(events) + (0 if lifecycle_event is None else 1)

    producer = EventHubProducerClient.from_connection_string(
        conn_str=connection_string,
        eventhub_name=args.event_hub,
    )

    try:
        before = partition_positions(producer)

        if args.replay_cadence_ms:
            cadence_seconds = args.replay_cadence_ms / 1000
            for obj in tqdm(
                events,
                desc="Publishing GPS",
                unit="event",
                dynamic_ncols=True,
            ):
                send_batch(producer, [obj], trip_id)
                time.sleep(cadence_seconds)
        else:
            with tqdm(
                total=len(events),
                desc="Publishing GPS",
                unit="event",
                dynamic_ncols=True,
            ) as progress:
                send_batch(producer, events, trip_id)
                progress.update(len(events))

        if lifecycle_event is not None:
            send_batch(producer, [lifecycle_event], trip_id)
            tqdm.write("Published trip_end")

        after, appended = wait_for_append(
            producer,
            before,
            expected_publish_count,
            args.verify_timeout_seconds,
        )
    finally:
        producer.close()

    print(f"event_hub={args.event_hub}")
    print(f"partition_positions_before={before}")
    print(f"partition_positions_after={after}")
    print(f"events_expected={expected_publish_count}")
    print(f"events_appended={appended}")
    print(f"trip_id={trip_id}")
    print(f"user_id={user_id}")
    print(f"device_id={device_id}")
    print(f"gps_events={len(events)}")
    print(f"ended_at={events[-1]['event_time']}")
    print(f"expected_last_sequence={events[-1]['sequence']}")
    print(f"trip_end={'no' if lifecycle_event is None else 'yes'}")

    if appended != expected_publish_count:
        raise SystemExit(
            "Event Hub verification failed: "
            f"expected {expected_publish_count} appended events, observed {appended}"
        )


if __name__ == "__main__":
    main()

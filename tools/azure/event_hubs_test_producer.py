"""Publish a bounded synthetic Canopy GPS trip to Azure Event Hubs.

The Event Hubs connection string is read from an environment variable so that
credentials never need to appear in command-line arguments or repository files.
This tool is for integration testing only; it is not deployed product code.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

CONNECTION_STRING_ENV = "CANOPY_EVENTHUB_SEND_CONNECTION_STRING"
DEFAULT_EVENT_HUB = "evh-canopy-gps-dev"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-hub", default=DEFAULT_EVENT_HUB)
    parser.add_argument("--points", type=int, default=320)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--speed-mps", type=float, default=4.2)
    parser.add_argument("--lat", type=float, default=37.5665)
    parser.add_argument("--lon", type=float, default=126.9780)
    parser.add_argument("--trip-id")
    parser.add_argument("--user-id", default="integration-user")
    parser.add_argument("--device-id", default="integration-device")
    return parser.parse_args(argv)


def build_events(args: argparse.Namespace) -> tuple[str, list[dict[str, object]]]:
    if args.points < 1:
        raise ValueError("--points must be >= 1")
    if args.interval_seconds <= 0:
        raise ValueError("--interval-seconds must be > 0")
    if args.speed_mps < 0:
        raise ValueError("--speed-mps must be >= 0")

    trip_id = args.trip_id or f"integration-{uuid.uuid4()}"
    start = datetime.now(timezone.utc).replace(microsecond=0)
    meters_per_lon_degree = 111_320.0 * math.cos(math.radians(args.lat))
    lon_step = args.speed_mps * args.interval_seconds / meters_per_lon_degree

    events: list[dict[str, object]] = []
    for index in range(args.points):
        event_time = start + timedelta(seconds=index * args.interval_seconds)
        events.append(
            {
                "schema_version": "canopy.gps.collector.v0.1",
                "event_id": str(uuid.uuid4()),
                "user_id": args.user_id,
                "device_id": args.device_id,
                "trip_id": trip_id,
                "sequence": index + 1,
                "event_time": event_time.isoformat().replace("+00:00", "Z"),
                "received_at": event_time.isoformat().replace("+00:00", "Z"),
                "lat": args.lat,
                "lon": args.lon + index * lon_step,
                "accuracy": 5.0,
                "speed": args.speed_mps,
                "altitude_m": 38.0,
                "vertical_accuracy": 5.0,
            }
        )
    return trip_id, events


def publish(connection_string: str, event_hub: str, events: list[dict[str, object]]) -> None:
    try:
        from azure.eventhub import EventData, EventHubProducerClient
    except ImportError as exc:
        raise RuntimeError(
            "azure-eventhub is required; install it with: pip install azure-eventhub"
        ) from exc

    producer = EventHubProducerClient.from_connection_string(
        conn_str=connection_string,
        eventhub_name=event_hub,
    )
    with producer:
        batch = producer.create_batch()
        for payload in events:
            encoded = json.dumps(payload, separators=(",", ":"))
            event = EventData(encoded)
            try:
                batch.add(event)
            except ValueError:
                if len(batch) == 0:
                    raise RuntimeError("single GPS event exceeds Event Hubs batch capacity")
                producer.send_batch(batch)
                batch = producer.create_batch()
                batch.add(event)
        if len(batch) > 0:
            producer.send_batch(batch)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    connection_string = os.environ.get(CONNECTION_STRING_ENV, "").strip()
    if not connection_string:
        print(
            f"missing {CONNECTION_STRING_ENV}; provide the send-only Event Hubs "
            "connection string through the environment",
            file=sys.stderr,
        )
        return 2

    trip_id, events = build_events(args)
    publish(connection_string, args.event_hub, events)
    print(f"published_points={len(events)}")
    print(f"trip_id={trip_id}")
    print(f"event_hub={args.event_hub}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

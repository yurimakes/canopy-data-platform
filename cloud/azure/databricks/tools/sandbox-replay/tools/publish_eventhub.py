#!/usr/bin/env python3
"""Replay a committed canonical GPS fixture to Azure Event Hubs."""
from __future__ import annotations
import argparse,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from azure.eventhub import EventData,EventHubProducerClient
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

def ts(s): return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()

def load_events(trip, duration):
    events=[json.loads(x) for x in (trip/"gps_raw.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if not events: raise SystemExit("empty fixture")
    if duration is not None:
        start=ts(events[0]["event_time"])
        events=[e for e in events if ts(e["event_time"])-start <= duration]
    if not events: raise SystemExit("duration cutoff selected no GPS events")
    return events

def fresh_identity(events):
    trip_id,user_id,device_id=str(uuid4()),str(uuid4()),str(uuid4())
    for event in events:
        event["event_id"]=str(uuid4())
        event["trip_id"]=trip_id
        event["user_id"]=user_id
        event["device_id"]=device_id
    return trip_id,user_id,device_id

def trip_end(events,campaign):
    first,last=events[0],events[-1]
    return {"event_id":str(uuid4()),"event_type":"trip_ended","schema_version":"trip-lifecycle-v1",
      "trip_id":first["trip_id"],"user_id":first["user_id"],"campaign_id":campaign,
      "started_at":first["event_time"],"ended_at":last["event_time"],
      "expected_last_sequence":last["sequence"],
      "occurred_at":datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
      "processing_generation":1,"result_owner":"databricks"}

def send_batch(producer, events, partition_key):
    batch=producer.create_batch(partition_key=partition_key)
    for obj in events:
        event=EventData(json.dumps(obj,separators=(",",":"),ensure_ascii=False))
        try: batch.add(event)
        except ValueError:
            producer.send_batch(batch)
            batch=producer.create_batch(partition_key=partition_key); batch.add(event)
    if len(batch): producer.send_batch(batch)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trip",type=Path,required=True)
    p.add_argument("--duration-seconds",type=float)
    p.add_argument("--replay-cadence-ms",type=int,default=0)
    p.add_argument("--no-trip-end",action="store_true")
    p.add_argument("--campaign-id",default="campaign_test")
    p.add_argument("--event-hub",default=os.getenv("EVENT_HUB_NAME","evh-canopy-sandbox-5dt016"))
    a=p.parse_args()
    if a.replay_cadence_ms<0: raise SystemExit("--replay-cadence-ms must be >= 0")
    conn=os.getenv("EVENT_HUB_CONNECTION_STRING")
    if not conn: raise SystemExit("EVENT_HUB_CONNECTION_STRING is required")
    events=load_events(a.trip,a.duration_seconds)
    trip_id,user_id,device_id=fresh_identity(events)
    producer=EventHubProducerClient.from_connection_string(conn_str=conn,eventhub_name=a.event_hub)
    try:
        if a.replay_cadence_ms:
            for obj in events:
                send_batch(producer,[obj],trip_id); time.sleep(a.replay_cadence_ms/1000)
        else: send_batch(producer,events,trip_id)
        if not a.no_trip_end: send_batch(producer,[trip_end(events,a.campaign_id)],trip_id)
    finally: producer.close()
    print(f"trip_id={trip_id}")
    print(f"user_id={user_id}")
    print(f"device_id={device_id}")
    print(f"gps_events={len(events)}")
    print(f"ended_at={events[-1]['event_time']}")
    print(f"expected_last_sequence={events[-1]['sequence']}")
    print(f"trip_end={'no' if a.no_trip_end else 'yes'}")

if __name__=="__main__": main()

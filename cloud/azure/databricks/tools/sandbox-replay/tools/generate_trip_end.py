#!/usr/bin/env python3
"""Generate trip_ended for a committed JSONL fixture at an arbitrary duration cutoff."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
def ts(s): return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
def main():
    p=argparse.ArgumentParser(); p.add_argument("--trip",type=Path,required=True)
    p.add_argument("--duration-seconds",type=float); p.add_argument("--campaign-id",default="campaign_test")
    a=p.parse_args(); events=[json.loads(x) for x in (a.trip/"gps_raw.jsonl").read_text().splitlines() if x.strip()]
    if not events: raise SystemExit("empty fixture")
    selected=events
    if a.duration_seconds is not None:
        start=ts(events[0]["event_time"]); selected=[e for e in events if ts(e["event_time"])-start <= a.duration_seconds]
        if not selected: raise SystemExit("cutoff precedes first GPS event")
    first,last=selected[0],selected[-1]
    obj={"event_id":str(uuid4()),"event_type":"trip_ended","schema_version":"trip-lifecycle-v1",
      "trip_id":first["trip_id"],"user_id":first["user_id"],"campaign_id":a.campaign_id,
      "started_at":first["event_time"],"ended_at":last["event_time"],"expected_last_sequence":last["sequence"],
      "occurred_at":datetime.now(timezone.utc).isoformat(timespec="milliseconds"),"processing_generation":1,"result_owner":"databricks"}
    print(json.dumps(obj,indent=2))
if __name__=="__main__": main()

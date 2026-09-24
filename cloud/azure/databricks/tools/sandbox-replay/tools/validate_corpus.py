#!/usr/bin/env python3
"""Validate a generated sandbox replay fixture corpus."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path,nargs="?",default=Path("sandbox-replay-fixtures"))
    a=p.parse_args()
    manifest=json.loads((a.root/"manifest.json").read_text(encoding="utf-8"))
    errors=[]; total=0
    names=[x["name"] for x in manifest["fixtures"]]
    if len(names)!=len(set(names)): errors.append("duplicate fixture names")
    for meta in manifest["fixtures"]:
        name=meta["name"]; d=a.root/"trips"/name
        expected=json.loads((d/"expected.json").read_text(encoding="utf-8"))
        events=[json.loads(line) for line in (d/"gps_raw.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        total += len(events)
        if len(events)!=meta["gps_rows"] or len(events)!=expected["gps_rows"]:
            errors.append(f"{name}: gps_rows mismatch")
        if not events:
            errors.append(f"{name}: empty"); continue
        seq=[e.get("sequence") for e in events]
        if seq != list(range(1,len(events)+1)): errors.append(f"{name}: non-contiguous sequence")
        if len({e.get("event_id") for e in events})!=len(events): errors.append(f"{name}: duplicate event_id")
        for key in ("trip_id","user_id","device_id"):
            if len({e.get(key) for e in events})!=1: errors.append(f"{name}: inconsistent {key}")
        times=[ts(e["event_time"]) for e in events]
        if any(b<a for a,b in zip(times,times[1:])): errors.append(f"{name}: timestamps not ordered")
        gap=max((b-a for a,b in zip(times,times[1:])),default=0.0)
        duration=times[-1]-times[0]
        if abs(gap-float(meta["max_adjacent_gap_seconds"]))>1e-6: errors.append(f"{name}: max gap mismatch")
        if abs(duration-float(meta["duration_seconds"]))>1e-6: errors.append(f"{name}: duration mismatch")
        if any(e.get("schema_version")!="canopy.gps.collector.v0.2" for e in events):
            errors.append(f"{name}: wrong GPS schema_version")
        print(f"PASS {name}: {len(events)} events, {duration:.1f}s, max_gap={gap:.1f}s")
    if errors:
        for e in errors: print("ERROR",e)
        raise SystemExit(1)
    print(f"PASS corpus: {len(names)} fixtures, {total} GPS events")

if __name__=="__main__": main()

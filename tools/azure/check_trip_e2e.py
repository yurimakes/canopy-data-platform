"""Opt-in live integration check. Uses existing resources; creates synthetic test Trips only.

Credentials: ignored apps/api/.local-data/azure-test-access.json (see apps/api/README.md).
Without --send-test, resumes the saved verification and sends no new GPS.
"""
import argparse
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from azure.cosmos import CosmosClient
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient
from fastavro import reader

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "apps/api/.local-data"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send-test", action="store_true", help="Create two synthetic Trips and send GPS to Azure")
    parser.add_argument("--confirm-test", action="store_true", help="Deprecated: use check_trip_feedback.py instead")
    parser.add_argument("--wait-seconds", type=int, default=660)
    args = parser.parse_args()
    if args.confirm_test:
        parser.error("Direct correction is retired. Use tools/azure/check_trip_feedback.py for feedback E2E.")
    cfg = json.loads((DATA / "azure-test-access.json").read_text(encoding="utf-8"))
    report_file = DATA / "azure-trip-e2e.json"
    tokens = cfg["tokens"]
    owner, other = "canopy-e2e-test", "hayden-device-test"

    def call(path, method="GET", body=None, user=owner, expected=(200,)):
        headers = {"x-functions-key": cfg["key"], "Content-Type": "application/json"}
        if user:
            headers["Authorization"] = "Bearer " + tokens[user]
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = Request(cfg["host"] + "/api/" + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=40) as response:
                code, raw = response.status, response.read()
        except HTTPError as error:
            code, raw = error.code, error.read()
        assert code in expected, f"{method} {path}: HTTP {code}, expected {expected}; {raw[:250]!r}"
        return json.loads(raw) if raw else None

    if args.send_test:
        report = {"source": "synthetic desktop HTTP test, NOT real iPhone GPS", "started_at": stamp(),
                  "trips": [], "checks": {}, "capture_complete": False}
        def save():
            report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        save()
        call("health")
        call("trips/start", "POST", {}, user=None, expected=(401,))
        call("trips/start", "POST", b"{", expected=(400,))
        call("gps", "POST", b"{", expected=(400,))
        report["checks"]["unauthenticated_and_invalid_json_rejected"] = True
        for mode in ("user", "developer"):
            request_id = str(uuid.uuid4())
            body = {"request_id": request_id, "device_id": "synthetic-e2e-" + mode}
            trip = call("trips/start", "POST", body, expected=(201,))
            record = {"trip_id": trip["trip_id"], "user_id": trip["user_id"], "mode": mode, "events": []}
            report["trips"].append(record)
            save()
            again = call("trips/start", "POST", body)
            assert again["trip_id"] == trip["trip_id"] and trip["status"] == "collecting"
            call("trips/start", "POST", {**body, "device_id": "different"}, expected=(409,))
            call("trips/" + trip["trip_id"], user=other, expected=(403, 404))
            for sequence in (1, 2):
                now = stamp()
                event = {"schema_version": "canopy.gps.collector.v0.2", "event_id": str(uuid.uuid4()),
                         "user_id": trip["user_id"], "device_id": body["device_id"], "trip_id": trip["trip_id"],
                         "sequence": sequence, "event_time": now, "received_at": now,
                         "lat": 37.5665, "lon": 126.978, "accuracy": 150, "speed": None,
                         "altitude_m": None, "vertical_accuracy_m": None, "course_deg": None,
                         "source": "expo-location.foreground", "collection_mode": mode,
                         "label": None if mode == "user" else "walk" if sequence == 1 else "bus",
                         "quality_flags": ["accuracy_above_100m", "speed_unavailable", "course_unavailable"],
                         "raw_location": {"timestamp": int(time.time()*1000), "coords": {"latitude": 37.5665,
                             "longitude": 126.978, "accuracy": 150, "speed": None, "heading": None,
                             "altitude": None, "altitudeAccuracy": None}},
                         "test_context": "synthetic desktop E2E; exclude from training"}
                record["events"].append(event)
                save()
                call("gps", "POST", event, expected=(202,))
                if sequence == 1:
                    call("gps", "POST", event, expected=(202,))
            # Desktop clocks can lag Azure on very short synthetic Trips. Let the
            # API timestamp this test stop; phone-provided end times are tested separately.
            stop = {"expected_last_sequence": 2}
            result = call(f"trips/{trip['trip_id']}/stop", "POST", stop, expected=(200, 202))
            assert result["status"] in ("processing", "ready")
            call(f"trips/{trip['trip_id']}/stop", "POST", stop, expected=(200, 202))
            record["stopped_at"] = stamp()
            save()
            print(f"HTTP PASS {mode}: {trip['trip_id']}", flush=True)
        report["checks"].update(duplicate_start=True, duplicate_stop=True, other_user_denied=True,
                               gps_null_and_low_accuracy_accepted=True, gps_duplicate_accepted=True)
        save()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    for trip in report["trips"]:
        if not trip.get("stopped_at"):
            result = call("trips/" + trip["trip_id"])
            if result["status"] == "collecting":
                result = call("trips/" + trip["trip_id"] + "/stop", "POST",
                              {"expected_last_sequence": len(trip["events"])}, expected=(200, 202))
            trip["stopped_at"] = result["ended_at"]
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    cosmos = CosmosClient(cfg["cosmos_endpoint"], credential=cfg["cosmos_readonly_key"])
    container = cosmos.get_database_client("canopy-db").get_container_client("trips")
    blob = BlobServiceClient(cfg["storage_url"], credential=AzureCliCredential()).get_container_client("raw")
    beginning = datetime.fromisoformat(report["started_at"]) - timedelta(minutes=10)
    ending = datetime.now(timezone.utc) + timedelta(seconds=args.wait_seconds)
    dates = {beginning.date(), ending.date()}
    prefixes = [f"gps/evhns-canopy-dev/evh-canopy-gps-dev/{partition}/{day:%Y/%m/%d}/"
                for partition in range(4) for day in dates]
    wanted = {e["event_id"]: e for t in report["trips"] for e in t["events"]}
    hits = {event_id: [] for event_id in wanted}
    raw_differences = {}
    seen = set()
    deadline = time.monotonic() + args.wait_seconds
    while True:
        ready = True
        for trip in report["trips"]:
            result = call("trips/" + trip["trip_id"])
            doc = container.read_item(trip["trip_id"], partition_key=trip["user_id"])
            assert doc["trip_id"] == result["trip_id"] and doc["user_id"] == trip["user_id"]
            assert doc["expected_last_sequence"] == 2
            if doc["status"] == "ready":
                assert doc["model_version"] == "mock_v1" and doc["segments"] == result["segments"]
            if doc["status"] == "failed":
                raise AssertionError(f"Trip failed: {doc.get('failed_step')} {doc.get('error_message')}")
            ready &= doc["status"] == "ready" and result["status"] == "ready"
            trip["cosmos"] = {k: doc[k] for k in ("id", "user_id", "status", "started_at", "ended_at", "model_version", "segments")}
        for prefix in prefixes:
            for item in blob.list_blobs(name_starts_with=prefix):
                key = (item.name, item.etag)
                # ADLS Gen2 directory entries can appear as zero-byte blobs.
                if key in seen or item.last_modified < beginning or item.size == 0:
                    continue
                if item.size > 16*1024*1024:
                    raise RuntimeError("Capture file exceeds 16 MiB test download limit; narrow the time range")
                payload = blob.download_blob(item.name).readall()
                for row in reader(io.BytesIO(payload)):
                    event = json.loads(row["Body"])
                    if not isinstance(event, dict) or event.get("event_id") not in wanted:
                        continue
                    expected = wanted[event["event_id"]]
                    if event != expected:
                        raw_differences[event["event_id"]] = {key: {"submitted": expected.get(key), "stored": event.get(key)}
                            for key in expected.keys() | event.keys()
                            if expected.get(key) != event.get(key) or (key in expected) != (key in event)}
                    hits[event["event_id"]].append(item.name)
                seen.add(key)
        report["checks"]["api_and_cosmos_ready_same_id"] = ready
        report["raw_paths_by_event"] = hits
        report["raw_differences"] = raw_differences
        report["capture_complete"] = all(len(hits[t["events"][0]["event_id"]]) >= 2
                                         and len(hits[t["events"][1]["event_id"]]) >= 1 for t in report["trips"])
        report["checks"]["raw_originals_identical"] = report["capture_complete"] and not raw_differences
        report["checked_at"] = stamp()
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Cosmos ready={ready}; Raw event IDs={sum(bool(v) for v in hits.values())}/{len(wanted)}; duplicate preservation={report['capture_complete']}; changed events={len(raw_differences)}", flush=True)
        if ready and report["capture_complete"]:
            if raw_differences:
                print("Capture contains all IDs, but Raw field values differ; see raw_differences in " + str(report_file), flush=True)
                raise AssertionError("Raw original comparison failed; details are saved in raw_differences")
            print("PASS: HTTP -> Cosmos lifecycle and GPS -> Event Hubs Capture -> Raw, all original fields preserved.", flush=True)
            print(report_file)
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Verification incomplete; rerun without --send-test to resume without new GPS")
        time.sleep(30)


if __name__ == "__main__":
    main()

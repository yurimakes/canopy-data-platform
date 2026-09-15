"""Preview/apply one container using the existing trips settings and Azure CLI login.

Only the observed Serverless account pattern is supported. Never creates a
database or provisioned throughput. Existing containers are verified, not changed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote


def az(*args):
    result = subprocess.run([shutil.which("az") or "az", *args, "--output", "json", "--only-show-errors"],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def clean(value):
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list): return [clean(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("subscription", "resource-group", "account", "database"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-container", default="trips")
    parser.add_argument("--container", default="trip_feedback")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    common = ["--subscription", args.subscription, "--resource-group", args.resource_group]
    account = az("cosmosdb", "show", "--name", args.account, *common)
    if "EnableServerless" not in {c["name"] for c in account["capabilities"]}:
        raise RuntimeError("Account is not the inspected Serverless pattern; review throughput before proceeding")
    existing = az("cosmosdb", "sql", "container", "list", "--account-name", args.account,
                  "--database-name", args.database, *common)
    reference = next(c["resource"] for c in existing if c["name"] == args.reference_container)
    if reference["partitionKey"]["paths"] != ["/user_id"]:
        raise RuntimeError("Reference container is not partitioned by user_id")
    keys = ("partitionKey", "indexingPolicy", "defaultTtl", "uniqueKeyPolicy", "conflictResolutionPolicy")
    resource = {"id": args.container, **{k: clean(reference[k]) for k in keys if reference.get(k) is not None}}
    plan = {"database": args.database, "container": args.container, "reference": args.reference_container,
            "throughput": "Serverless; no provisioned RU/s", "consistency": account["consistencyPolicy"],
            "resource": resource}
    target = next((c["resource"] for c in existing if c["name"] == args.container), None)
    if target is None and args.apply:
        uri = ("https://management.azure.com" + account["id"] + "/sqlDatabases/" + quote(args.database, safe="")
               + "/containers/" + quote(args.container, safe="") + "?api-version=2024-05-15")
        with tempfile.TemporaryDirectory(prefix="canopy-feedback-provision-") as directory:
            body = Path(directory)/"container.json"
            body.write_text(json.dumps({"properties": {"resource": resource, "options": {}}}), encoding="utf-8")
            az("rest", "--method", "put", "--url", uri, "--body", "@" + str(body))
        for attempt in range(24):
            try:
                target = az("cosmosdb", "sql", "container", "show", "--account-name", args.account,
                            "--database-name", args.database, "--name", args.container, *common)["resource"]
                break
            except subprocess.CalledProcessError as error:
                if error.returncode != 3 or attempt == 23: raise
                time.sleep(5)  # ARM creation can return before the container is readable.
    if target is not None:
        for key in keys:
            if clean(target.get(key)) != clean(reference.get(key)):
                raise RuntimeError("Existing feedback container differs from reference: " + key)
        plan["status"] = "verified existing container"
    else:
        plan["status"] = "preview only; use --apply to create"
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

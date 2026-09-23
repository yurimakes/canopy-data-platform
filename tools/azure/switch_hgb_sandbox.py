"""Switch the existing app endpoints between production and the HGB sandbox."""
import argparse
import json
from pathlib import Path
import subprocess
from uuid import uuid5, NAMESPACE_URL

SUBSCRIPTION = "27db5ec6-d206-4028-b5e1-6004dca5eeef"
GROUP = "5dt-2nd-team1"
APP = "func-canopy-dev"
HOST = "https://adb-7405612422597045.5.azuredatabricks.net"
ROUTES = {
    "sandbox": {"EVENTHUB_NAME": "evh-canopy-sandbox-5dt024", "TRIP_DATABRICKS_JOB_ID": "1025081607321226"},
    "production": {"EVENTHUB_NAME": "evh-canopy-gps-dev", "TRIP_DATABRICKS_JOB_ID": "32875321236425"},
}


def az_json(executable, *args):
    result = subprocess.run([executable, *args, "--subscription", SUBSCRIPTION, "-o", "json"],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Azure command failed: " + result.stderr)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=ROUTES)
    parser.add_argument("--az", default="az")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    current = {s["name"]: s["value"] for s in az_json(args.az, "functionapp", "config", "appsettings", "list", "-g", GROUP, "-n", APP)}
    required = {"TRIP_DATABRICKS_HOST": HOST, "TRIP_DATABRICKS_DISPATCH_MODE": "resident",
                "TRIP_RESULT_OWNER": "databricks", "EVENTHUB_FQDN": "evhns-canopy-dev.servicebus.windows.net"}
    if any(current.get(k) != v for k, v in required.items()):
        raise RuntimeError("Current server is not the expected main Azure resident-worker configuration")
    print(json.dumps({"before": {k: current.get(k) for k in ROUTES[args.target]}, "after": ROUTES[args.target]}))
    if args.apply:
        # The existing Function identity has hub-scoped RBAC, not namespace-wide RBAC.
        identity = az_json(args.az, "functionapp", "identity", "show", "-g", GROUP, "-n", APP)
        hub = ROUTES[args.target]["EVENTHUB_NAME"]
        scope = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.EventHub/namespaces/evhns-canopy-dev/eventhubs/{hub}"
        existing = az_json(args.az, "role", "assignment", "list", "--assignee-object-id", identity["principalId"], "--scope", scope)
        for role in ("Azure Event Hubs Data Sender", "Azure Event Hubs Data Receiver"):
            if not any(r.get("roleDefinitionName")==role for r in existing):
                az_json(args.az, "role", "assignment", "create", "--assignee-object-id", identity["principalId"],
                    "--assignee-principal-type", "ServicePrincipal", "--role", role, "--scope", scope,
                    "--name", str(uuid5(NAMESPACE_URL, scope+identity["principalId"]+role)))
        group = current.get("TRIP_EVENTHUB_CONSUMER_GROUP")
        if group and group != "$Default":
            az_json(args.az, "eventhubs", "eventhub", "consumer-group", "create", "-g", GROUP,
                    "--namespace-name", "evhns-canopy-dev", "--eventhub-name", hub, "--name", group)
        az_json(args.az, "functionapp", "config", "appsettings", "set", "-g", GROUP, "-n", APP,
                "--settings", *[k+"="+v for k,v in ROUTES[args.target].items()])
        saved = {s["name"]:s["value"] for s in az_json(args.az,"functionapp","config","appsettings","list","-g",GROUP,"-n",APP)}
        if any(saved.get(k)!=v for k,v in ROUTES[args.target].items()):
            raise RuntimeError("Route read-back differs")
        print("Route verified; no mobile binary or Function code was deployed.")


if __name__ == "__main__":
    main()

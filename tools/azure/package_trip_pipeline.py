"""Package existing modules and a manual test Job. Does not deploy or run Azure."""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PIPELINES = "cloud/azure/pipelines/databricks/"
FILES = [PIPELINES + "finalize_trip_pipeline.py", PIPELINES + "trip_prediction_wait.py", PIPELINES + "trip_job.py",
         "cloud/azure/functions/func_canopy_dev/carbon_calculator.py",
         "cloud/azure/functions/func_canopy_dev/carbon_policy.yaml",
         *["apps/api/services/" + name for name in
           ("trip_carbon.py", "trip_processor.py", "mock_trip_processor.py", "cosmos_service.py")]]


def package(output, workspace_root, gold_root, cosmos_endpoint, secret_scope=None, secret_key=None, iphone=False, final_segment_table=None):
    if not workspace_root.startswith("/Workspace/") or ".." in workspace_root.split("/"):
        raise ValueError("workspace_root must be an absolute Workspace directory")
    if "/pipeline_test/" not in gold_root or not gold_root.startswith("abfss://"):
        raise ValueError("use an isolated abfss://.../pipeline_test/... Gold root")
    if bool(secret_scope) != bool(secret_key):
        raise ValueError("both secret scope and key are required")
    workspace_root, gold_root = workspace_root.rstrip("/"), gold_root.rstrip("/")
    runner = workspace_root + "/" + PIPELINES + "finalize_trip_pipeline.py"
    gold = gold_root + "/final_trips"
    trip_id, user_id, campaign = "pipeline_test_trip_1", "pipeline_test_user_1", "pipeline_test_campaign_1"
    sample = {"completed_at": "2026-09-16T01:11:00+00:00", "trip": {
        "trip_id": trip_id, "user_id": user_id, "campaign_id": campaign,
        "processing_generation": 1,
        "started_at": "2026-09-16T01:00:00+00:00", "ended_at": "2026-09-16T01:10:00+00:00"}}
    import sys
    sys.path.insert(0, str(ROOT / "apps/api"))
    from services.mock_trip_processor import ConfirmationFixtureProcessor
    sample["result"] = ConfirmationFixtureProcessor().process_trip(sample["trip"])
    def task(name, parameters, dependencies=()):
        return {"task_key": name, "environment_key": "trip_env", "timeout_seconds": 900,
                "max_retries": 0, "depends_on": [{"task_key": d} for d in dependencies],
                "spark_python_task": {"python_file": runner, "source": "WORKSPACE",
                                      "parameters": parameters}}
    publish = ["publish", "--gold-path", gold, "--trip-id", trip_id, "--user-id", user_id,
               "--allow-test-create", "--cosmos-endpoint", cosmos_endpoint,
               "--cosmos-database", "canopy-db", "--cosmos-container", "trips"]
    if secret_scope:
        publish += ["--cosmos-secret-scope", secret_scope, "--cosmos-secret-key", secret_key]
    job = {"name": "canopy-trip-finalization-test", "max_concurrent_runs": 1,
           "timeout_seconds": 1800, "performance_target": "STANDARD",
           "environments": [{"environment_key": "trip_env", "spec": {"environment_version": "4",
               "dependencies": ["PyYAML==6.0.3", "azure-cosmos==4.17.0", "azure-identity==1.25.3"]}}],
           "tasks": [task("finalize_gold", ["finalize", "--gold-path", gold, "--input", workspace_root + "/sample_input.json", "--allow-test-create"]),
                     task("publish_cosmos", publish, ["finalize_gold"])]}
    if iphone:
        if not secret_scope:
            raise ValueError("The phone Job needs the existing Cosmos secret scope/key")
        job.update(max_concurrent_runs=3, queue={"enabled": True}, parameters=[
            {"name": "end_event", "default": "{}"}, {"name": "input_mode", "default": "ml"},
            {"name": "final_segment_table", "default": final_segment_table or ""}])
        job["tasks"] = [{"task_key": "finalize_stopped_trip", "environment_key": "trip_env",
            "timeout_seconds": 1500, "max_retries": 0, "spark_python_task": {
                "python_file": workspace_root + "/" + PIPELINES + "trip_job.py", "source": "WORKSPACE",
                "parameters": ["--end-event", "{{job.parameters.end_event}}",
                    "--input-mode", "{{job.parameters.input_mode}}",
                    "--final-segment-table", "{{job.parameters.final_segment_table}}",
                    "--gold-path", gold_root + "/iphone_final_trips", "--queue-path", gold_root + "/iphone_wait",
                    "--cosmos-endpoint", cosmos_endpoint, "--secret-scope", secret_scope,
                    "--cosmos-secret-key", secret_key]}}]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            data = (ROOT / name).read_bytes()
            if name.endswith(".py"):
                compile(data, name, "exec")
            archive.writestr(name, data)
        archive.writestr("sample_input.json", json.dumps(sample, indent=2))
        archive.writestr("trip_finalization_job.json", json.dumps(job, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--gold-root", required=True)
    parser.add_argument("--cosmos-endpoint", required=True)
    parser.add_argument("--secret-scope")
    parser.add_argument("--secret-key")
    parser.add_argument("--final-segment-table", help="Agreed completed ML result table; no prediction fallback")
    parser.add_argument("--iphone", action="store_true", help="Package the existing Job for Event Hubs-triggered phone Trips")
    parser.add_argument("--output", default=str(ROOT / "data/interim/trip-finalization.zip"))
    args = parser.parse_args()
    print(package(args.output, args.workspace_root, args.gold_root, args.cosmos_endpoint,
                  args.secret_scope, args.secret_key, args.iphone, args.final_segment_table))

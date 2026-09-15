"""Build locally. Does not create/update a Databricks Job or any Azure resource."""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = "cloud/azure/pipelines/databricks/"
FILES = [
    "shared/configs/baseline_eligibility.yaml",
    *[RUNTIME + name for name in ("baseline_policy.yaml", "baseline_eligibility.py",
                                  "build_personal_baseline.py", "build_global_baseline.py",
                                  "run_eligible_baselines.py")],
]


def package(output, workspace_root):
    if not workspace_root.startswith("/Workspace/") or ".." in workspace_root.split("/"):
        raise ValueError("workspace_root must be an absolute /Workspace/ deployment directory")
    runner = workspace_root.rstrip("/") + "/" + RUNTIME + "run_eligible_baselines.py"
    # A fragment for the two Baseline tasks only. Weekly Gold is owned by its author.
    tasks = []
    for phase, dependency in (("personal", "build_weekly_summary"), ("global", "build_personal_baseline")):
        params = ["--phase", phase, "--campaign-id", "{{job.parameters.campaign_id}}"]
        if phase == "global":
            params += ["--evaluation-week", "{{job.parameters.evaluation_week}}"]
        tasks.append({"task_key": f"build_{phase}_baseline", "depends_on": [{"task_key": dependency}],
                      "spark_python_task": {"python_file": runner, "parameters": params},
                      "environment_key": "canopy_env"})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            data = (ROOT / name).read_bytes()
            if name.endswith(".py"):
                compile(data, name, "exec")
            archive.writestr(name, data)
        archive.writestr("baseline_eligibility_tasks.json", json.dumps({"tasks": tasks}, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output", default=str(ROOT / "data/interim/baseline-eligibility.zip"))
    args = parser.parse_args()
    print(package(args.output, args.workspace_root))

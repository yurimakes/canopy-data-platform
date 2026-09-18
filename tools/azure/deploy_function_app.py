"""공용 Function App 통합 배포. 기본값은 검증·압축만 수행."""
import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from package_trip_api import package, REQUIRED_FUNCTIONS


def az(*args):
    command = shutil.which("az") or shutil.which("az.cmd")
    if not command:
        raise RuntimeError("Azure CLI가 필요합니다.")
    completed = subprocess.run([command, *args, "-o", "json"],
                               capture_output=True, text=True, check=True)
    return json.loads(completed.stdout) if completed.stdout.strip() else None


def live_functions(group, name):
    return {item["name"].rsplit("/", 1)[-1] for item in az(
        "functionapp", "function", "list", "-g", group, "-n", name
    )}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--resource-group", default="5dt-2nd-team1")
    parser.add_argument("--name", default="func-canopy-dev")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = package(root)
    archive = shutil.make_archive(str(target.parent / "func_canopy_dev"), "zip", target)
    if not args.deploy:
        print(f"검증된 통합 배포본: {archive}")
        return
    expected = set(json.loads((target / "function-manifest.json").read_text())["functions"])
    before = live_functions(args.resource_group, args.name)
    missing = before - expected
    if missing:
        raise RuntimeError(f"현재 서버 함수가 배포본에서 누락됨. 배포 중단: {sorted(missing)}")
    az("functionapp", "deployment", "source", "config-zip", "-g", args.resource_group,
       "-n", args.name, "--src", archive, "--build-remote", "true")
    for _ in range(30):
        current = live_functions(args.resource_group, args.name)
        if (before | REQUIRED_FUNCTIONS) <= current:
            print(json.dumps({"verified_functions": sorted(current)}, ensure_ascii=False))
            return
        time.sleep(10)
    raise RuntimeError(f"배포 후 함수 누락: {sorted((before | REQUIRED_FUNCTIONS) - current)}")


if __name__ == "__main__":
    main()

"""Build an additive Functions package locally. Does not contact/deploy to Azure."""
from pathlib import Path
import shutil
import copy
import zipfile


REQUIRED_FUNCTIONS = {
    "health", "GpsIngest", "gps_smoke", "carbon_smoke", "cosmos_smoke",
    "keyvault_smoke", "mission_get", "ranking_get", "account_auth",
    "user_register", "trip_start", "trip_stop", "trip_get", "trip_list", "trip_confirm",
    "trip_feedback", "place_search", "transit_route_search", "trip_worker",
    "trip_end_received",
    "community_get", "notification_read", "journey_action", "mission_action", "trip_comparison",
}

DOMAIN_FILES=[
    *['tools/local/'+name+'.py' for name in ('business','community_service','projections','rewards','reward_baselines','journey_rewards','activity','flow_recovery','weekly_publication','population','model','commute')],
    'cloud/azure/functions/func_canopy_dev/mission_policy.yaml',
    'shared/configs/local_reward_extensions.json',
]


def validate_package(target: Path):
    """외부 서비스 호출 없이 전체 함수의 import와 트리거 등록 확인."""
    import json
    import os
    import subprocess
    import sys

    script = (
        "import json; from function_app import app; "
        "print(json.dumps([f.get_function_name() for f in app.get_functions()]))"
    )
    env = dict(os.environ, TRIP_DATABRICKS_ENABLED="true", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=target, env=env,
        capture_output=True, text=True, check=True,
    )
    names = json.loads(result.stdout.strip().splitlines()[-1])
    missing = REQUIRED_FUNCTIONS - set(names)
    if missing or len(names) != len(set(names)):
        raise ValueError(f"Function registration incomplete: missing={sorted(missing)}")
    (target / "function-manifest.json").write_text(
        json.dumps({"functions": sorted(names)}, indent=2), encoding="utf-8"
    )
    return names


def patch_deployed(source: Path, output: Path, root: Path):
    """Preserve the live team package; replace only our Trip integration modules."""
    owned = ["trip_routes.py", *["services/" + n for n in
        ("runtime.py", "trip_service.py", "cosmos_service.py", "trip_lifecycle.py", "trip_dispatch.py", "user_registration.py", "accounts.py")]]
    with zipfile.ZipFile(source) as previous, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in previous.infolist():
            if info.filename not in owned:
                target.writestr(copy.copy(info), previous.read(info.filename))
        for name in owned:
            body = (root / "apps/api" / name).read_bytes()
            compile(body, name, "exec")
            info = copy.copy(previous.getinfo(name)) if name in previous.namelist() else zipfile.ZipInfo(name)
            # Python's default writestr permissions are 0600, unreadable by the Linux worker.
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, body)
    return output


def package(root: Path,include_runtime=False):
    source = root / "cloud/azure/functions/func_canopy_dev"
    api = root / "apps/api"
    target = (api / "build/func_canopy_dev").resolve()
    if target.parent != (api / "build").resolve():
        raise ValueError("Package path is outside apps/api/build")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    # 공용 폴더의 신규 함수와 정책 파일도 배포에 포함. 비밀 설정과 개발 파일은 제외.
    for item in source.iterdir():
        if item.is_file() and item.suffix in {".py", ".yaml", ".yml", ".json"}:
            if item.name != "local.settings.json":
                shutil.copy2(item, target / item.name)
        elif item.is_dir() and (item / "__init__.py").exists():
            shutil.copytree(item, target / item.name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*"))
    shutil.copy2(api / "trip_routes.py", target / "trip_routes.py")
    shutil.copytree(api / "services", target / "services", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in DOMAIN_FILES:
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/name,destination)
    dependencies = (source / "requirements.txt").read_text() + "\n" + (api / "requirements.txt").read_text()
    (target / "requirements.txt").write_text(dependencies, encoding="utf-8")
    if include_runtime:
        from package_runtime_assets import package as bundle_assets
        import json,hashlib
        bundle=root/'.local-data/release/runtime-assets.zip'
        bundle_assets(root,bundle)
        with zipfile.ZipFile(bundle) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            for name,digest in manifest.items():
                destination=(target/'runtime-assets'/name).resolve()
                if not destination.is_relative_to((target/'runtime-assets').resolve()):raise ValueError('unsafe asset path')
                payload=archive.read(name)
                if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('asset checksum mismatch')
                destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(payload)
        with (target/'requirements.txt').open('a',encoding='utf-8') as file:
            file.write('\ncatboost>=1.2,<2\npandas>=2.2,<3\npyproj>=3.6,<4\n')
    validate_package(target)
    print(target)
    return target


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime-assets',action='store_true')
    args=parser.parse_args()
    package(Path(__file__).resolve().parents[2],include_runtime=args.with_runtime_assets)

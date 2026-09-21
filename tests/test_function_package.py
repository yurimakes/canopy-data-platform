"""통합 배포에서 팀 함수 또는 계정·Trip이 누락되면 실패해야 함."""
import importlib.util
import shutil
import subprocess
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("packager", ROOT / "tools/azure/package_trip_api.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.fixture
def packaged(tmp_path):
    for name in ["cloud/azure/functions/func_canopy_dev", "apps/api"]:
        shutil.copytree(ROOT / name, tmp_path / name,
                        ignore=shutil.ignore_patterns(".venv", "build", ".local-data", "__pycache__", ".env*"))
    for name in packager.DOMAIN_FILES:
        destination=tmp_path/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,destination)
    return packager.package(tmp_path)


def test_all_function_groups_registered(packaged):
    names = set(packager.validate_package(packaged))
    assert packager.REQUIRED_FUNCTIONS <= names
    assert (packaged / "mission_policy.yaml").is_file()
    assert (packaged / "ranking_api.py").is_file()
    assert not (packaged / "local.settings.json").exists()

def test_mobile_function_key_cannot_call_diagnostics_or_legacy_principal_routes(packaged):
    script="""
from function_app import app
names={'gps_smoke','cosmos_smoke','keyvault_smoke','mission_get','ranking_get'}
for function in app.get_functions():
    if function.get_function_name() in names:
        binding=next(b for b in function.get_bindings_dict()['bindings'] if b['type']=='httpTrigger')
        assert binding['authLevel'].value=='admin'
"""
    env={**os.environ,'CANOPY_COMMUNITY_ENABLED':'true'};env.pop('PYTHONPATH',None)
    subprocess.run([sys.executable,'-c',script],cwd=packaged,env=env,check=True,capture_output=True)


def test_missing_ranking_dependency_blocks_package(packaged):
    (packaged / "ranking_api.py").unlink()
    with pytest.raises(subprocess.CalledProcessError):
        packager.validate_package(packaged)


def test_missing_trip_registration_blocks_package(packaged):
    entry = packaged / "function_app.py"
    entry.write_text(entry.read_text(encoding="utf-8").replace(
        "app.register_functions(trip_blueprint)", ""), encoding="utf-8")
    with pytest.raises(ValueError, match="registration incomplete"):
        packager.validate_package(packaged)

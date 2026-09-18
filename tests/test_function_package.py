"""통합 배포에서 팀 함수 또는 계정·Trip이 누락되면 실패해야 함."""
import importlib.util
import shutil
import subprocess
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
    return packager.package(tmp_path)


def test_all_function_groups_registered(packaged):
    names = set(packager.validate_package(packaged))
    assert packager.REQUIRED_FUNCTIONS <= names
    assert (packaged / "mission_policy.yaml").is_file()
    assert (packaged / "ranking_api.py").is_file()
    assert not (packaged / "local.settings.json").exists()


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

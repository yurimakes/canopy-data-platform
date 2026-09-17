"""Build an additive Functions package locally. Does not contact/deploy to Azure."""
from pathlib import Path
import shutil
import copy
import zipfile


def patch_deployed(source: Path, output: Path, root: Path):
    """Preserve the live team package; replace only our Trip integration modules."""
    owned = ["trip_routes.py", *["services/" + n for n in
        ("runtime.py", "trip_service.py", "cosmos_service.py", "trip_lifecycle.py", "trip_dispatch.py")]]
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


def package(root: Path):
    source = root / "cloud/azure/functions/func_canopy_dev"
    api = root / "apps/api"
    target = (api / "build/func_canopy_dev").resolve()
    if target.parent != (api / "build").resolve():
        raise ValueError("Package path is outside apps/api/build")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("host.json", "function_app.py", "carbon_calculator.py", "carbon_policy.yaml"):
        shutil.copy2(source / name, target / name)
    with (target / "function_app.py").open("a", encoding="utf-8") as stream:
        stream.write("\nfrom trip_routes import bp as trip_blueprint\napp.register_functions(trip_blueprint)\n")
    shutil.copy2(api / "trip_routes.py", target / "trip_routes.py")
    shutil.copytree(api / "services", target / "services", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    dependencies = (source / "requirements.txt").read_text() + "\n" + (api / "requirements.txt").read_text()
    (target / "requirements.txt").write_text(dependencies, encoding="utf-8")
    print(target)
    return target


if __name__ == "__main__":
    package(Path(__file__).resolve().parents[2])

"""Build an additive Functions package locally. Does not contact/deploy to Azure."""
from pathlib import Path
import shutil


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

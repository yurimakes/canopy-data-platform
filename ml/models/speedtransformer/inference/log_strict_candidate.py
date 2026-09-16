"""Log the verified strict candidate as a loadable MLflow pyfunc, without Registry writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ARTIFACT_SHA256 = "55D5EA590D8B3405852632A6E470BB161CF448A6A19185399F4D237D8555736F"
HERE = Path(__file__).resolve().parent
MODEL_CODE = HERE.parent / "artifacts" / "playground_v1" / "code" / "model_utils.py"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def extract_verified_artifact(archive: Path, destination: Path) -> dict:
    if _sha256(archive.read_bytes()) != ARTIFACT_SHA256:
        raise ValueError("strict candidate ZIP SHA256 mismatch")
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read("manifest.json"))
        if manifest.get("artifact_version") != "speedtransformer-strict-large-seed316-v1":
            raise ValueError("unexpected strict candidate artifact version")
        for name, checksum_key in (("model.pt", "model_sha256"), ("scaler.json", "scaler_sha256")):
            data = source.read(name)
            if _sha256(data) != manifest[checksum_key].upper():
                raise ValueError(f"{name} SHA256 mismatch")
            (destination / name).write_bytes(data)
        (destination / "manifest.json").write_bytes(source.read("manifest.json"))
    return manifest


def main() -> None:
    # MLflow prints a Unicode run link when closing a run; Windows may default
    # to cp949 even when the model and run were logged successfully.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-zip", type=Path, required=True)
    parser.add_argument("--tracking-uri", default="databricks://CANOPY")
    parser.add_argument("--experiment", default="/Shared/CANOPY_SpeedTransformer_Strict")
    args = parser.parse_args()

    import mlflow

    with tempfile.TemporaryDirectory() as temp:
        artifact_dir = Path(temp)
        manifest = extract_verified_artifact(args.artifact_zip, artifact_dir)
        mlflow.set_tracking_uri(args.tracking_uri)
        mlflow.set_experiment(args.experiment)
        with mlflow.start_run() as run:
            mlflow.set_tags({"artifact_version": manifest["artifact_version"], "candidate": "true"})
            info = mlflow.pyfunc.log_model(
                name="model",
                python_model=str(HERE / "strict_pyfunc.py"),
                code_paths=[str(MODEL_CODE)],
                artifacts={
                    "checkpoint": str(artifact_dir / "model.pt"),
                    "scaler": str(artifact_dir / "scaler.json"),
                    "manifest": str(artifact_dir / "manifest.json"),
                },
                pip_requirements=[
                    "mlflow>=3,<4", "numpy>=2.1,<3", "pandas>=2.2,<3", "torch>=2.11,<2.12"
                ],
                metadata={
                    "artifact_version": manifest["artifact_version"],
                    "classes": ["bike", "bus", "car", "train", "walk"],
                },
            )
            print(f"run_id={run.info.run_id}")
            print(f"model_uri={info.model_uri}")
            print(f"runs_uri=runs:/{run.info.run_id}/model")


if __name__ == "__main__":
    main()

"""Stage and validate mode-detection runtime assets before deployment."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

MODEL_NAME = "aihub_canonical_raw120.joblib"
TRANSIT_FILES = (
    "seoul_bus_stops.csv",
    "seoul_bus_route_stops.csv",
    "subway_stations.csv",
    "korail_stations.csv",
)

EXPECTED_FEATURES = (
    "distance_m",
    "displacement_m",
    "straightness_ratio",
    "mean_speed_mps",
    "max_speed_mps",
    "speed_std_mps",
    "mean_abs_acceleration_mps2",
    "acceleration_std_mps2",
    "stop_ratio",
    "mean_heading_change_deg",
    "altitude_range_m",
    "accuracy_mean_m",
    "accuracy_std_m",
    "accuracy_missing_ratio",
    "altitude_missing_ratio",
    "valid_point_ratio",
)


def validate_model(path: Path) -> None:
    import joblib

    bundle = joblib.load(path)
    if not isinstance(bundle, dict):
        raise ValueError("model artifact must be a dictionary bundle")
    required = {"model", "feature_columns", "classes", "window_duration_seconds"}
    missing = required - set(bundle)
    if missing:
        raise ValueError(f"model artifact missing keys: {sorted(missing)}")
    if tuple(bundle["feature_columns"]) != EXPECTED_FEATURES:
        raise ValueError("model artifact is not the expected 16-feature robust HGBC")
    if int(bundle["window_duration_seconds"]) != 120:
        raise ValueError("model artifact does not use a 120-second window")
    if type(bundle["model"]).__name__ != "HistGradientBoostingClassifier":
        raise ValueError(
            "expected HistGradientBoostingClassifier, got "
            f"{type(bundle['model']).__name__}"
        )


def stage_model(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    validate_model(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    validate_model(destination)


def stage_transit(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    missing = [name for name in TRANSIT_FILES if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"transit source is missing required files: {', '.join(missing)}"
        )
    for name in TRANSIT_FILES:
        shutil.copy2(source_dir / name, destination_dir / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Path to authoritative aihub_canonical_raw120.joblib",
    )
    parser.add_argument(
        "--transit-dir",
        type=Path,
        default=None,
        help="Optional directory containing all four authoritative transit CSVs",
    )
    args = parser.parse_args()

    bundle_root = Path(__file__).resolve().parents[1]
    stage_model(args.model, bundle_root / "assets" / "models" / MODEL_NAME)
    if args.transit_dir is not None:
        stage_transit(args.transit_dir, bundle_root / "assets" / "transit")

    print(f"staged model: {bundle_root / 'assets' / 'models' / MODEL_NAME}")
    if args.transit_dir is None:
        print("transit CSVs: not staged (ML-only fallback remains available)")
    else:
        print(f"staged transit CSVs: {bundle_root / 'assets' / 'transit'}")


if __name__ == "__main__":
    main()

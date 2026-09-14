# SpeedTransformer runtime integration

Canopy runtime integration for the registered AI Hub speed-only SpeedTransformer champion.

The model-development source of truth remains `aletheia-ops/speedtransformer-aihub`. This directory contains only the Canopy-facing runtime contract and registry integration.

## Layout

- `configs/`: registry/runtime contract metadata.
- `inference/`: MLflow/Unity Catalog model loading and invocation helpers.
- `features/`: Canopy-side feature/window construction. Intentionally empty until the segment-to-200-point policy is finalized.
- `tests/`: runtime contract/parity tests.

## Stable input contract

- one inference row contains one `speed_sequence`
- raw unit: km/h
- exactly 200 values
- finite values only
- `0 <= speed <= 200`
- output classes: `bike`, `bus`, `car`, `train`, `walk`

The registered MLflow package owns StandardScaler application, model reconstruction, checkpoint loading, and class decoding. Canopy must not duplicate those preprocessing artifacts in Git.

## Explicitly not stored here

- `best_macro_model.pth`
- `scaler.joblib`
- `label_encoder.joblib`
- training datasets
- experiment reports and ablation launchers

Those binaries belong to MLflow / Unity Catalog; training and research history remain in `speedtransformer-aihub`.

## Window-policy TODO

The champion requires exactly 200 transitions. Canopy still needs an explicit policy for:

- confirmed segments longer than 200 points;
- confirmed segments shorter than 200 points;
- trip-end flushing/fallback behavior.

Do not silently pad, truncate, or aggregate until that policy is selected and tested.

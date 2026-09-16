# Transition LightGBM model

This directory adapts the upstream `riekim/canopy-transition-model` LightGBM transportation-mode classifier for the Canopy data platform and Databricks MLflow.

## Upstream

- Repository: `https://github.com/riekim/canopy-transition-model`
- Original author: riekim
- License: MIT (see `LICENSE.upstream`)
- The feature engineering and LightGBM training logic are preserved, but the notebook-style script has been refactored into callable functions with explicit configuration and MLflow logging.

## Inputs

`train_lgbm_model.py` expects a directory containing:

- `train_10000.parquet`
- `val_3000.parquet`

Required raw columns:

- `trip_id`
- `latitude`
- `longitude`
- `timestamp`
- `mode`

The original labels are mapped as follows:

| Original | Mode | Compact |
|---:|---|---:|
| 0 | Walk | 0 |
| 1 | Bike | 1 |
| 2 | Car | 2 |
| 3 | Bus | 3 |
| 5 | Subway | 4 |

## MLflow contract

The logged MLflow model is the native LightGBM classifier and accepts the 17 engineered features produced by `preprocessing.py`.

Trip-level rolling majority smoothing and short-segment cleanup are deliberately **not** embedded in the model artifact. They require trajectory context and remain explicit post-processing/evaluation logic.

Each run logs:

- LightGBM hyperparameters
- data split limits and smoothing parameters
- train/validation/test row counts
- smoothed test accuracy and macro F1
- per-class precision/recall/F1
- feature contract
- label mapping
- runtime contract
- classification report
- native LightGBM MLflow model with inferred signature and input example

## Local run

```bash
cd ml/models/transition_detector
python -m pip install -r requirements.txt
python train_lgbm_model.py \
  --data-dir /path/to/od_gps_processed \
  --experiment-name canopy-transition-lgbm
```

## Databricks run

Upload/sync this directory to the Databricks workspace or repository, install `requirements.txt`, and run:

```bash
python train_lgbm_model.py \
  --data-dir /Volumes/<catalog>/<schema>/<volume>/od_gps_processed \
  --experiment-name /Shared/canopy-transition-lgbm
```

To register the resulting model, add:

```bash
--registered-model-name <catalog>.<schema>.<model_name>
```

Do not hard-code a tracking URI for Databricks. The Databricks runtime configures MLflow tracking automatically.

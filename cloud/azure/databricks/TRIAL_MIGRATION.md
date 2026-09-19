# Trial migration runbook

This branch migrates the mode-inference pipeline into **dbw-canopy-trial**.

## Safety boundary

- Legacy `dbw-canopy-dev` / `CANOPY_DEV`: **read-only reference only**.
- Trial `dbw-canopy-trial` / `CANOPY_TRIAL`: **the only mutation/deployment target**.

## Trial contracts

```text
Input:
dbw_canopy_trial.sandbox.silver_gps_observations

Output:
dbw_canopy_trial.sandbox.silver_mode_predictions

Runtime artifact:
dbfs:/Volumes/dbw_canopy_trial/ml/runtime_artifacts/canopy_transition_lgbm_pointwise_v1.skops
```

Operational timestamps preserved for later latency testing:

```text
silver_gps_observations.validated_at
  -> mode_inference_features.features_processed_at
  -> silver_mode_predictions.predicted_at
```

## 1. Read-only legacy artifact check

```bash
databricks fs ls \
  dbfs:/Volumes/dbw_canopy_dev/ml/runtime_artifacts \
  -p CANOPY_DEV
```

Expected source:

```text
canopy_transition_lgbm_pointwise_v1.skops
```

Download the source artifact locally. This reads legacy only.

```bash
mkdir -p .migration-artifacts

databricks fs cp \
  dbfs:/Volumes/dbw_canopy_dev/ml/runtime_artifacts/canopy_transition_lgbm_pointwise_v1.skops \
  .migration-artifacts/canopy_transition_lgbm_pointwise_v1.skops \
  -p CANOPY_DEV
```

## 2. Trial volume

Inspect Trial first:

```bash
databricks volumes list dbw_canopy_trial ml -p CANOPY_TRIAL
```

If `runtime_artifacts` does not exist, create a managed Trial volume:

```bash
databricks volumes create \
  dbw_canopy_trial \
  ml \
  runtime_artifacts \
  MANAGED \
  -p CANOPY_TRIAL
```

## 3. Upload into Trial

```bash
databricks fs cp \
  .migration-artifacts/canopy_transition_lgbm_pointwise_v1.skops \
  dbfs:/Volumes/dbw_canopy_trial/ml/runtime_artifacts/canopy_transition_lgbm_pointwise_v1.skops \
  --overwrite \
  -p CANOPY_TRIAL
```

Verify the Trial target:

```bash
databricks fs ls \
  dbfs:/Volumes/dbw_canopy_trial/ml/runtime_artifacts \
  -l \
  -p CANOPY_TRIAL
```

## 4. Bundle validation and deployment

From this repository on `feature/trial-migration`:

```bash
databricks bundle validate -t trial
databricks bundle deploy -t trial
```

Do not deploy this branch with `CANOPY_DEV`.

## 5. Runtime smoke test

The ingestion layer must already provide:

```text
dbw_canopy_trial.sandbox.silver_gps_observations
```

Start/update the Trial mode-inference pipeline and verify that rows appear in:

```text
dbw_canopy_trial.sandbox.silver_mode_predictions
```

Latency benchmarking is deferred until all intended layers are connected.

## Registered-model note

Runtime inference loads the native `skops` artifact from the Trial UC Volume. The configured `models:/dbw_canopy_trial.ml.canopy_transition_lgbm_pointwise/1` URI is currently used as model identity metadata rather than as the runtime artifact transport.

A corresponding Trial registered-model object should be migrated before declaring the ML/lineage layer fully self-contained, but it is not required for the native LightGBM runtime to load the `skops` file.

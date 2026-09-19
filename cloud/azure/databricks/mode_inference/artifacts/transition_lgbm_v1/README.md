# Transition LightGBM runtime artifact

This migration branch targets the Trial workspace only.

Reference source (read-only legacy):
```text
models:/dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise/1
```

Do not modify the legacy workspace during migration.

Trial runtime target:
```text
/Volumes/dbw_canopy_trial/ml/runtime_artifacts/canopy_transition_lgbm_pointwise_v1.skops
```

The Lakeflow runtime loads the native LightGBM `skops` artifact directly from the Trial Unity Catalog Volume. The registered-model URI is retained as model identity metadata; runtime inference does not download the model through MLflow at startup.

For local parity/reference work only, the native source artifact may be staged under:
```text
mode_inference/artifacts/transition_lgbm_v1/model.skops
```

The Trial deployment is considered self-contained only after the artifact exists in `dbw_canopy_trial.ml.runtime_artifacts`.

# Transition LightGBM runtime artifact

Place the registered model's native `model.skops` file in this directory before deploying.

Expected runtime file:

```text
mode_inference/artifacts/transition_lgbm_v1/model.skops
```

Source registered model:

```text
models:/dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise/1
```

The streaming runtime loads this native LightGBM artifact directly with `skops`.
It does not download the model through MLflow at pipeline startup.

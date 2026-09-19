PIPELINE B POINTWISE IMPLEMENTATION

## 1. Repository

Created a new standalone Git repository:

```text
/home/aletheia/projects/canopy-mode-inference-pipeline
Branch: main
Preferred remote: aletheia-ops/canopy-mode-inference-pipeline
```

No GitHub remote was created because remote creation was not required to complete implementation. The existing Pipeline A repository was not modified.

An ignored `.venv` contains local test tooling, including PySpark 4.2.0. PySpark is not a Lakeflow runtime dependency.

## 2. Architecture implemented

```text
dbw_canopy_dev.silver.gps_observations (read-only)
        |
        v
transformWithState keyed by trip_id
        |
        v
private mode_inference_features (17 features)
        |
        v
MLflow LightGBM pointwise inference
        |
        v
dbw_canopy_dev.silver.mode_predictions
```

The implementation contains separate modules for configuration, contracts, feature engineering, state, model inference, and Lakeflow declarations. It does not implement smoothing, transition cleanup, segmentation, SpeedTransformer, Pipeline C, trip finalization, or Gold output.

Pipeline B owns only `silver.mode_predictions`. It does not declare, adopt, refresh, or modify legacy `silver.gps_features` or `silver.mode_segments`.

## 3. Registered model inspection

Read-only Unity Catalog inspection found:

```text
Registered model: dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise
Available versions: 1
Version 1 status: READY
Aliases: none
Champion: absent
Resolved URI: models:/dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise/1
Run ID: 23e0964e882b45d1854424e7d344a105
Flavors: lightgbm, python_function
```

Direct MLflow registry inspection verified the signature. Inputs are exactly the approved 17 named, required `double` columns in contract order. Output is a one-dimensional `int64` tensor. The signature exposes class predictions only, not probabilities.

No registry alias or model metadata was mutated.

## 4. Input contract

Pipeline B reads these Pipeline A fields:

```text
trip_id    -> trip grouping
sequence   -> canonical append order
event_time -> model timestamp and output trajectory time
lat        -> reference latitude
lon        -> reference longitude
event_id, user_id -> preserved output identity
```

Pipeline A `raw_speed` is intentionally not an input feature. The model's `speed` is calculated from coordinate displacement and elapsed event time.

## 5. Feature engineering

The implementation matches `canopy-transition-model-mlflow/preprocessing.py` from commit `8375722267041a88834bd24add7494d3c17b0646`:

- haversine distance with Earth radius 6,371,000 metres;
- elapsed seconds clamped to at least 0.1;
- derived speed in km/h;
- acceleration from derived speed and elapsed seconds;
- bearing and folded absolute bearing change;
- point-count rolling windows with `min_periods=1` behavior;
- pandas sample standard deviation semantics with initial zero;
- pandas linear 0.25/0.75 quantiles;
- stop threshold `speed < 3.0 km/h`.

The model feature tuple is explicit and order-checked at runtime.

## 6. Stateful processing

`TripFeatureProcessor` uses Spark 4 row-based `transformWithState`, keyed by `trip_id`, in append mode with no time mode.

Within each input iterator, rows are ordered by `(sequence, event_time, event_id)`. State contains:

- the last 151 raw GPS points;
- the last emitted sequence;
- all seen `event_id` values for the retained trip state.

Before processing a new point, the raw history is bounded so the current point plus 150 predecessors are available. This preserves the predecessor required to calculate the earliest speed in `speed_mean_150` and `stop_count_150`.

Duplicate event IDs, duplicate sequences, and sequences behind the emitted frontier are ignored. No historical prediction is rewritten.

## 7. Reference parity results

**17-feature parity: PASS.**

Deterministic tests compared every feature against the pinned Pandas reference for trajectories of 1, 2, 4, 6, 11, 31, 61, 151, and 176 points. Test data includes irregular intervals, zero-displacement stops, movement, and changing bearings.

State was advanced in multiple batches with reversed within-batch input order. Output retained exact parity after the 151-point state rollover. Explicit assertions cover:

```text
speed_mean_150
stop_count_150
speed_q25_60
speed_q75_60
accel_std_30
```

Floating-point comparison uses `rtol=1e-9`, `atol=1e-8`.

## 8. Model inference path

Production inference uses `mlflow.pyfunc.spark_udf` with the configured registered-model URI. The 17 named feature columns are passed as a single named Spark struct so MLflow receives the exact signature names rather than ordinal columns. The UDF is constructed once in pipeline graph evaluation and is not loaded once per row.

Compact classes map as follows:

```text
0 walk
1 bike
2 car
3 bus
4 subway
```

`confidence` is a nullable double and is always null for this model version because its packaged signature returns only class IDs. No confidence is invented.

Read-only registered-model parity passed: version 1 was loaded through the Unity Catalog MLflow URI and produced identical compact classes to the pinned local source artifact for seven rows representing different feature-history states.

Status: model class parity is proven through MLflow PyFunc locally; the Spark UDF itself has not yet been executed on Databricks serverless.

## 9. mode_predictions contract

Implemented public contract:

```text
event_id          STRING NOT NULL
user_id           STRING NOT NULL
trip_id           STRING NOT NULL
sequence          BIGINT NOT NULL
event_time        TIMESTAMP NOT NULL
predicted_class   INT NOT NULL
predicted_mode    STRING NOT NULL
confidence        DOUBLE
model_name        STRING NOT NULL
model_version     STRING
predicted_at      TIMESTAMP NOT NULL
```

`event_time` is preserved from the observation for downstream timeline reconstruction. `predicted_at` is processing time.

## 10. Tests

Validation results:

```text
python -m compileall -q mode_inference tests
PASS

pytest -q tests/unit
25 passed

pytest -q tests/spark
12 passed, 2 skipped

pytest -q (default offline suite)
37 passed, 2 skipped

registered-model parity test (explicit read-only URI)
1 passed
```

The two default Spark-suite skips are disclosed:

1. Spark DDL parsing requires a local JVM; Java is not installed on this host.
2. Registered-model access is opt-in and skipped without `CANOPY_REGISTERED_MODEL_URI`; it was then run explicitly and passed.

The Spark-named reference/state tests exercise the exact production feature and state-transition functions, but a live streaming `transformWithState` query was not started locally.

## 11. Bundle design

Created an independent Asset Bundle:

```text
Bundle: canopy-mode-inference
Resource key: mode_inference_pipeline
Name: canopy-mode-inference-pipeline-${bundle.target}
Catalog: dbw_canopy_dev
Schema: silver
Serverless: true
Channel: CURRENT
Continuous: not configured
Orchestration Job: none
```

Parameters cover catalog, input observations table, output predictions table, model URI, state-timeout policy, and timezone. Development defaults use explicit model version 1 and UTC.

Read-only bundle validation result:

```text
Validation OK!
```

No deployment, pipeline creation, Job creation, table operation, or live input read occurred.

## 12. Known limitations

- **Out-of-order events:** ordering is deterministic within one state call, but a row arriving with `sequence` at or behind the already emitted frontier is ignored. Append-only output does not rewrite prior predictions.
- **Exact parity versus late insertion:** inserting a late point into historical trajectory order would change later rolling features. Exact correction is fundamentally incompatible with the chosen append-only first version without retractions/upserts or trip finalization.
- **State/history:** raw feature context is bounded at 151 points, but the seen-event-ID set grows for the life of each trip state. No state timeout is applied. Long-lived/unbounded trips require future state-lifecycle design.
- **Short trips:** predictions are emitted from the first point. This exactly matches `min_periods=1`, including zero-valued first-point motion features, but early predictions necessarily have little trajectory context.
- **Confidence:** unavailable from the registered artifact and therefore null.
- **Registered-model testing:** the deployed version's metadata/signature and PyFunc class predictions were verified read-only. The production `mlflow.pyfunc.spark_udf` path has not been executed on Databricks serverless.
- **Spark integration:** local PySpark 4.2.0 is installed, but the host lacks Java. The local JVM-backed schema test skipped, and an end-to-end streaming state query remains for Databricks validation.
- **State timeout:** configuration currently accepts only `none`; implementing a timer requires an explicit trip-lifecycle policy.

## 13. Readiness for Databricks validation

**Ready for Databricks validation: yes.**

The repository is source-complete, feature parity passes, registered-model class parity passes, and the bundle validates. The next step should be a non-deploying temporary Databricks Spark 4 integration run that exercises:

1. `transformWithState` state schema and row API;
2. multi-batch state rollover and late/duplicate behavior;
3. MLflow Spark UDF loading of explicit version 1;
4. public output schema projection.

Per task constraints, that serverless validation was not started. Production deployment should wait for it.

# Canopy Mode Inference Pipeline

## Purpose

This repository is the standalone Pipeline B for raw, pointwise transportation-mode inference:

```text
Pipeline A
Event Hubs -> dbw_canopy_trial.sandbox.silver_gps_observations

Pipeline B (this repository)
gps_observations
  -> exact model feature engineering
  -> pointwise LightGBM inference
  -> dbw_canopy_trial.sandbox.silver_mode_predictions

Future work, outside this repository's current scope
mode_predictions -> smoothing / segmentation -> mode_segments
```

Pipeline B reads Pipeline A output but does not own or modify it. It owns only `dbw_canopy_trial.sandbox.silver_mode_predictions`. The feature dataset is a private Lakeflow table.

## Model

Trial migration configuration records the equivalent model identity:

```text
models:/dbw_canopy_trial.ml.canopy_transition_lgbm_pointwise/1
```

There is currently no `Champion` alias. The inspected version is READY and its signature contains exactly 17 required double columns in the order defined by `mode_inference.contracts.FEATURE_NAMES`. Its output is an `int64` class tensor. The artifact does not expose probabilities, so public `confidence` is null.

Compact classes map to `walk`, `bike`, `car`, `bus`, and `subway` for values 0 through 4.

## Feature engineering

The implementation is behaviorally pinned to `canopy-transition-model-mlflow/preprocessing.py` at source commit `8375722267041a88834bd24add7494d3c17b0646`.

Features use `trip_id`, `event_time`, `lat`, and `lon`. The `raw_speed` value from Pipeline A is deliberately not a model feature: model `speed` is derived from haversine coordinate displacement and elapsed time and is expressed in km/h.

The implementation preserves reference behavior:

- elapsed seconds clamped to a minimum of `0.1`;
- point-count rolling windows with `min_periods=1` behavior;
- sample standard deviation (`ddof=1`) and zero for a single point;
- linear 0.25/0.75 quantiles;
- stop threshold `speed < 3.0 km/h`;
- first-point speed, acceleration, distance, and bearing change equal to zero.

## Stateful streaming semantics

Spark 4 `transformWithState` maintains independent state per `trip_id`. Rows within each input iterator are sorted by `(sequence, event_time, event_id)`. State is stored natively as scalar metadata plus a bounded `ListState` of up to 151 raw observations, so the earliest speed in a 150-speed rolling window still has its predecessor. The previous monolithic JSON state has been removed.

This first version is intentionally append-only:

- an unseen row with a sequence greater than the last emitted sequence is processed;
- a duplicate `event_id`, duplicate sequence, or row arriving behind the emitted sequence frontier is ignored;
- historical predictions are not rewritten when a late row arrives;
- duplicate tracking is bounded to the retained 151-point history; sequence monotonicity remains the primary guard against reprocessing older rows;
- per-trip state uses a processing-time TTL; the current placeholder is 2 hours and resets whenever the trip state is updated.

This is deterministic, but exact reference parity for a late point inserted before already emitted points is fundamentally incompatible with append-only output. Producers must deliver each trip close to sequence order. A later design should use the existing `trip_ended` lifecycle signal for deterministic cleanup; TTL remains a fallback for abandoned trips or missing lifecycle events.

## Public output

`dbw_canopy_trial.sandbox.silver_mode_predictions` contains one raw pointwise prediction per accepted source event:

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

`event_time` remains the trajectory timeline for future segmentation. `predicted_at` is operational processing time only.

## Configuration

The Asset Bundle parameterizes catalog, input table, output table, model URI, state-timeout policy, and UTC timezone. It creates a distinct `canopy-mode-inference` bundle with pipeline resource key `mode_inference_pipeline`, CURRENT channel, and serverless compute. The migration branch keeps serverless Lakeflow, a 1-second trigger interval, and the continuous orchestration Job from the verified inference branch.

## Testing

Create the ignored local environment and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test,spark]'
.venv/bin/python -m pytest -q
```

The deterministic test oracle is a pinned copy of the reference preprocessing implementation. It covers short trips and boundaries above 5, 10, 30, 60, and 150 points; irregular time intervals; zero displacement; changing bearing; stop/move behavior; state rollover; sequence ordering; duplicate protection; and trip isolation.

The registered-model comparison is opt-in and read-only:

```bash
DATABRICKS_CONFIG_PROFILE=CANOPY_TRIAL \
CANOPY_REGISTERED_MODEL_URI=models:/dbw_canopy_trial.ml.canopy_transition_lgbm_pointwise/1 \
.venv/bin/python -m pytest -q \
  tests/spark/test_model_parity.py::test_registered_model_matches_pinned_local_artifact
```

Local PySpark requires a JVM. If Java is unavailable, the DDL parser test skips; reference feature/state parity still runs as pure deterministic processor tests.

## Out of scope

This implementation does not perform smoothing, transition cleanup, segmentation, trip finalization, SpeedTransformer inference, Pipeline C processing, or Gold-table writes. It does not adopt or touch inactive legacy `gps_features` or `mode_segments` tables.

# GPS streaming first layer

This package defines the Canopy GPS streaming path from Event Hubs through
stateful mode segmentation and bounded SpeedTransformer inference.

## Runtime contract

- `speed_min_60s` is calculated for `(event_time - 60 s, event_time]` and is
  persisted with each enriched Silver point.
- The mock detector accepts `speed_min_60s` but deliberately ignores it.
- Each mock segment target is selected uniformly from 250 through 300 derived
  speed points, inclusive.
- Weak mode/confidence values are replayable for a fixed seed and `trip_id` and
  remain metadata only.
- Invalid transitions reset incomplete mock-segment state so a strong-model
  window never bridges rejected data.
- The first observation has no derived transition, so at least 251 GPS
  observations are required to produce the minimum 250-point mock segment.

## SpeedTransformer contract

`segment_inference.py` implements the bounded handoff to the MLflow pyfunc:

- every inference window contains exactly 200 derived speeds in km/h;
- 200-249 usable speeds produce one representative window;
- 250-300 usable speeds produce three evenly distributed representative
  windows;
- longer segments use a bounded number of representative windows covering the
  beginning and end;
- window probability vectors are averaged before the final segment `argmax`;
- weak predictions are retained only as metadata;
- incomplete persisted history returns `insufficient_history` without invoking
  MLflow.

The intended Unity Catalog model URI for development is:

`models:/dbw_canopy_dev.ml.canopy_speedtransformer@champion`

## Stateful processing

`transform_with_state.py` binds the framework-neutral GPS runtime to Python Row
`transformWithState`:

- one versioned JSON `ValueState` is stored per `trip_id`;
- rows are ordered deterministically inside each key/micro-batch;
- state restores the previous observation, rolling-speed state, detector
  target/count, segment progress, and deterministic mock RNG state;
- tagged `feature` and `segment` rows are routed idempotently by Delta `MERGE`.

The current mock detector version is `mock-random-v2`. Persisted targets outside
250-300 are rejected rather than silently coerced.

## Medallion objects

Development defaults resolve to:

- `dbw_canopy_dev.bronze.gps_events`
- `dbw_canopy_dev.silver.gps_observations`
- `dbw_canopy_dev.silver.gps_quarantine`
- `dbw_canopy_dev.silver.gps_features`
- `dbw_canopy_dev.silver.mode_segments`
- `dbw_canopy_dev.gold.mode_segment_predictions`
- registered model namespace: `dbw_canopy_dev.ml`

`CanopyTableConfig` rejects `default` / `information_schema` and requires
Bronze, Silver, Gold, and ML schemas to be distinct.

## Serverless Lakeflow deployment target

The deployed target is a **serverless Lakeflow ETL pipeline**, not classic Jobs
compute.

- `resources/gps_streaming.pipeline.yml` defines the serverless pipeline.
- `resources/gps_streaming.job.yml` defines a continuous Job that orchestrates
  the pipeline and is intentionally deployed in `PAUSED` state.
- The pipeline uses the Preview channel because the current design depends on
  Lakeflow `foreach_batch_sink`.
- `lakeflow_pipeline.py` declares the Event Hubs -> Bronze -> Silver graph,
  applies row-based `transformWithState`, and routes stateful and inference
  micro-batches through Lakeflow-managed ForEachBatch sinks.
- Lakeflow owns query lifecycle and checkpoints. The old five manually managed
  checkpoint directories are not part of the serverless deployment contract.
- `job.py` and the explicit Structured Streaming `start_*` functions are kept as
  a classic compatibility/reference path; they are not referenced by the
  current serverless bundle resources.

The pipeline remains logically triggered; the continuous Job controls
continuous execution. This avoids user-selected DBR, node type, worker count,
compute policy, and access-mode configuration.

## Event Hubs

The Lakeflow source uses the Kafka-compatible Event Hubs endpoint with
`SASL_SSL` / `PLAIN`.

Safe bundle configuration contains only:

- bootstrap server;
- Event Hub entity name;
- dedicated consumer-group name;
- Databricks secret scope/key names.

The listen-only connection string must live only in Databricks Secrets.

## Python dependencies

`requirements.lakeflow.txt` contains the SpeedTransformer runtime dependencies:
MLflow, PyTorch, NumPy, pandas, scikit-learn, and joblib. Do not install
PySpark into the pipeline environment.

## Validation status

Repository-side unit tests cover the neutral runtime, state serialization,
mock detector, ingestion contracts, and bounded inference. `TwsTester` still
requires Spark 4 / a Databricks integration environment.

Before any real deployment or Event Hubs consumption, follow
`WORKSPACE_PROVISIONING.md`. The bundle/job must remain paused until the schema,
Event Hubs security, secret, and registered-model prerequisites are satisfied.

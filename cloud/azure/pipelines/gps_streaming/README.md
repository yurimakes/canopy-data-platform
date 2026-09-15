# GPS streaming first layer

This package defines the stateful core between Silver GPS speed points and the
first-layer segment contract.

Current integration behavior:

- `speed_min_60s` is calculated for `(event_time - 60 s, event_time]` and must
  be persisted with each enriched Silver point.
- The mock detector accepts `speed_min_60s` as part of its input contract but
  deliberately ignores it.
- Each mock segment target is selected uniformly from 250 through 300 derived
  speed points, inclusive.
- The weak mode and confidence are random but replayable for a fixed seed and
  `trip_id`.
- An unfinished trip tail below its random target is not emitted as a closed
  segment. This prevents an ineligible segment from reaching SpeedTransformer.
- Weak output remains metadata and must not be passed into SpeedTransformer as
  a feature or prior.

The core has no Spark dependency. `transform_with_state.py` binds it to DBR
17.3's Python Row `transformWithState` API. The adapter stores one versioned
JSON `ValueState` per `trip_id`, sorts each key's rows inside a micro-batch,
restores the neutral runtime, and writes `EnrichedSpeedPoint` and
`SegmentEvent` records to their respective Delta tables. The future real
detector should implement the same `process(DetectorPoint)` boundary.

## Closed-segment inference

`segment_inference.py` defines the bounded handoff to the existing MLflow
pyfunc model:

- The default representative-window policy emits 1 window for 200–249 speed
  points and 3 windows for the mock detector's 250–300 range.
- The first and last eligible portions of longer segments are always covered.
- MLflow receives one pandas row per window in the single `speed_sequence`
  column; every row contains exactly 200 raw km/h values.
- Window probability vectors are averaged, then `argmax` produces the strong
  segment mode. The random weak mode remains output metadata only.
- A segment whose persisted history has not yet reached its detector-declared
  `speed_point_count` returns `insufficient_history` without invoking MLflow,
  even if 200 rows are already visible. The Databricks adapter treats this as
  retryable because Delta visibility may lag segment closure.

## Databricks adapter

`databricks_adapter.py` supplies the thin workspace layer:

- reads only `closed` segment micro-batches;
- skips segments that already have a `scored` prediction;
- range-joins each remaining segment to ordered Silver speed history;
- loads the MLflow pyfunc lazily and reuses it on the stream driver;
- records `insufficient_history` while leaving that segment retryable; and
- uses Delta `MERGE` on `segment_id` so checkpoint or micro-batch retries are
  idempotent.

Workspace-specific values are deliberately required at deployment time:
`model_uri` and `checkpoint_location`. `CanopyTableConfig` makes the catalog,
all three schema names, and every table basename configurable. Development
defaults resolve to `dbw_canopy_dev.bronze`, `.silver`, and `.gold`; using the
Unity Catalog `default` schema for any pipeline layer is rejected.

## GPS preprocessing

`gps_preprocessing.py` defines the upstream point contract:

- parses the intended `canopy.gps.collector.v0.1` payload;
- preserves the producer's `speed` value unchanged until its unit is confirmed;
- derives km/h with Haversine distance (`R = 6,371,000 m`) and the actual
  positive timestamp interval, so spacing need not be exactly one second;
- retains `dt_s` and `distance_m` for QC and future first-layer features;
- rejects, rather than clips, non-finite, non-positive-time, or above-200-km/h
  transitions; and
- resets partial mock-segment state after an invalid transition so a model
  window never bridges rejected data.

The first observation in a trip has no derived transition. Consequently, a
mock segment cannot close before 251 GPS observations produce its minimum 250
derived speed points. SpeedTransformer inference windows remain exactly 200
derived speed points.

## Spark ingestion boundary

`spark_ingestion.py` contains the runtime-stable PySpark layer:

- maps the Event Hubs Kafka envelope to an append-only Bronze Delta table;
- parses the collector JSON with an explicit schema;
- separates validated observations from quarantine records;
- applies event-time watermarking and `event_id` deduplication; and
- creates the Bronze, parsed-observation, quarantine, feature, and mock-segment
  table contracts.

The stateful observation-to-feature step uses Python Row
`transformWithState`, `TimeMode.None`, append output, and a RocksDB state store.
The tagged operator output is routed in one `foreachBatch`; Delta `MERGE` on
`event_id` and `segment_id` makes partial sink success and batch retry safe.

## Asset Bundle template

`databricks.yml` and `resources/gps_streaming.job.yml` define a development
target for the verified `dbw-canopy-dev` workspace. The template selects DBR
17.3 LTS, Standard access mode, the existing Job Compute policy, explicit
RocksDB/Avro state-store settings, and parameterizes table names, checkpoint
root, Event Hubs non-secret settings, secret lookup names, and MLflow model URI.

The template is configuration only. Read-only `bundle validate` and
`bundle sync --dry-run` checks pass for `CANOPY_DEV`; it has not been synced or
deployed. See `WORKSPACE_PROVISIONING.md` before running any bundle command
that changes workspace state.

# GPS streaming first layer

This package defines the stateful core between Silver GPS speed points and the
first-layer segment contract.

Current integration behavior:

- `speed_min_60s` is calculated for `(event_time - 60 s, event_time]` and must
  be persisted with each enriched Silver point.
- The mock detector accepts `speed_min_60s` as part of its input contract but
  deliberately ignores it.
- Each mock segment target is selected uniformly from 200 through 300 derived
  speed points, inclusive.
- The weak mode and confidence are random but replayable for a fixed seed and
  `trip_id`.
- An unfinished trip tail below its random target is not emitted as a closed
  segment. This prevents an ineligible segment from reaching SpeedTransformer.
- Weak output remains metadata and must not be passed into SpeedTransformer as
  a feature or prior.

The core has no Spark dependency. A Databricks adapter can keep one instance of
the state per trip in its stateful operator and write `EnrichedSpeedPoint` and
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
`model_uri` and `checkpoint_location`. The default logical tables are
`canopy.silver.gps_features`, `canopy.silver.mode_segments`, and
`canopy.gold.mode_segment_predictions`.

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

The first observation in a trip has no derived transition. Consequently, 201
GPS observations are required to produce 200 derived speed points.

## Spark ingestion boundary

`spark_ingestion.py` contains the runtime-stable PySpark layer:

- maps the Event Hubs Kafka envelope to an append-only Bronze Delta table;
- parses the collector JSON with an explicit schema;
- separates validated observations from quarantine records;
- applies event-time watermarking and `event_id` deduplication; and
- creates the Bronze, parsed-observation, quarantine, feature, and mock-segment
  table contracts.

The stateful observation-to-feature step is intentionally not bound to a Spark
API yet. Apache Spark 4 identifies `TransformWithState` as the successor to
`applyInPandasWithState`; the correct implementation therefore depends on the
selected Databricks Runtime. The framework-neutral core will be reused either
way.

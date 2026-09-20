# Integrated mode inference + segmentation replay pipeline

This isolated trial pipeline combines the existing pointwise LightGBM inference
path with a new incremental finalizer. It does not replace or write to the
tables owned by the existing inference and segment-generation bundles.

## Architecture

```text
replay GPS stream
  -> TripFeatureProcessor
  -> replay_integrated_enriched_mode_predictions (internal streaming table)
       -> public replay_integrated_mode_predictions
       -> PredictionEvent --+
                            +-> union -> TripSegmentationProcessor
trip-ended stream ----------+              -> replay_integrated_mode_segments
```

The enriched prediction path adds `lat` and `lon` in an internal persisted
streaming table shared by both downstream flows, so model inference runs once
and both consumers observe the same `predicted_at`. The public
prediction table retains the existing `MODE_PREDICTIONS_SCHEMA_DDL`. The
segment output is a native streaming table; the critical path has no
stream-stream join and no `foreachBatch` append.

The bundle builds one wheel containing the new package and the existing
`mode_inference` package from `../inference/mode_inference`. This reuses the
verified feature processor and model loader without copying their source.

## State and readiness

Each trip uses typed Spark `ValueState` with a processing-time TTL. The state
contains:

- the next required sequence (valid trips start at sequence `1`);
- pending out-of-order points and a sequence-to-payload fingerprint map;
- three raw and two repaired tail points for the two smoothing passes;
- compact completed/current segment accumulators;
- trip-end metadata, emitted generations, the sealed final sequence, and a
  conflict flag.

Predictions advance only as a contiguous prefix. Final rows are emitted after a
valid Databricks-owned trip end exists and every sequence through
`expected_last_sequence` has arrived. A trip end behind the processed prefix,
an extra pending point beyond the declared end, a conflicting prediction at an
existing sequence, or conflicting metadata for one processing generation
marks the trip conflicted and blocks output.

Exact prediction and trip-end replays are ignored. Output IDs are deterministic
per `(trip_id, processing_generation, segment_index)`, and emitted generations
are retained in checkpointed state. State changes and native table output are
committed through Structured Streaming checkpoint semantics rather than manual
`foreachBatch` idempotency.

## Smoothing and segments

The processor reproduces the existing two-pass rule with two-point lookahead:

1. repair the immediate return after a first mode transition;
2. remove isolated one-point mode islands.

Both rules require adjacent event-time gaps not exceeding
`max_repair_gap_seconds`. Consecutive stabilized modes form one segment.
Distances sum Haversine edges internal to each final segment using Earth radius
`6_371_008.8` metres.

## Trial deployment

From this directory:

```bash
databricks bundle validate -t trial
databricks bundle deploy -t trial
```

Deployment is intentionally manual. The pipeline expects the replay GPS and
trip-ended inputs configured in `databricks.yml` and owns:

- `dbw_canopy_trial.sandbox.replay_integrated_mode_predictions`
- `dbw_canopy_trial.sandbox.replay_integrated_enriched_mode_predictions` (internal)
- `dbw_canopy_trial.sandbox.replay_integrated_mode_segments`

## Local verification

```bash
uv run --extra test pytest tests -q
uv build --wheel --out-dir dist
```

Inference compatibility tests remain in `../inference/tests`.

## Known limitations

- State is TTL-bounded but sequence fingerprints and compact completed segments
  grow with trip length; valid ingestion sequences are capped at `10_000_000`.
- Once a completion seals a trip, any genuinely new later prediction conflicts
  with that trip. Reprocessing uses a higher `processing_generation` with the
  same sealed sequence range.
- Append-only streaming cannot retract rows if a conflicting duplicate appears
  only after a generation has already been committed. Such a late conflict is
  retained in state and blocks later generations; upstream quarantine remains
  necessary for correction workflows.
- This prototype has not yet demonstrated lower latency. Benchmarking is a
  separate coordinator task after review and deployment.

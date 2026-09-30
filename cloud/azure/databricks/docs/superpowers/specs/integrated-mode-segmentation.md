# Integrated Mode Segmentation Specification

This specification adopts `canopy_integrated_pipeline_work_mode_handoff(1).md`
as the architecture brief and records the decisions made during implementation.

## Required behavior

- Add an isolated replay/sandbox Lakeflow pipeline; do not replace the existing
  inference or segment-generation pipelines.
- Reuse the existing inference feature processor and model implementation.
- Persist the existing public pointwise prediction contract for observability.
- Feed an internal enriched prediction event containing latitude and longitude
  into a per-trip `transformWithState` segmentation processor.
- Normalize enriched predictions and trip-ended rows to one union-compatible
  stream. Do not use a stream-stream join or `foreachBatch` output sink.
- Valid trips contain every integer prediction sequence from `1` through
  `expected_last_sequence`.
- Exact prediction replays are ignored. A different payload for an already-seen
  `(trip_id, sequence)` invalidates the trip and prevents segment emission.
- Conflicting trip-ended payloads for the same generation likewise fail closed.
- Incremental smoothing must match the existing two-pass Spark reference:
  transition-lag repair followed by singleton-island repair, each subject to
  `max_repair_gap_seconds`.
- Segment indices are one-based and IDs are
  `{trip_id}:g{processing_generation}:segment:{segment_index}`.
- Segment distance uses Haversine edges internal to the stabilized segment and
  Earth radius `6_371_008.8` metres.
- Native checkpointed streaming output and deterministic IDs provide replay
  idempotency. A finalized generation emits at most once per state checkpoint.
- Per-trip state uses processing-time TTL. Out-of-order predictions are retained
  until the contiguous prefix can advance; the ingestion contract bounds valid
  sequence values at `10_000_000`.
- A trip end whose expected final sequence is behind an already-advanced
  contiguous prefix is treated as conflicting and fails closed. This preserves
  incremental compaction without silently truncating already-processed points.

## Output contract

The segment output preserves the existing fields:

`trip_id`, `user_id`, `processing_generation`, `segment_index`, `segment_id`,
`mode`, `start_sequence`, `end_sequence`, `start_time`, `end_time`,
`point_count`, `distance_m`, `confidence`, `model_name`, `model_version`,
`latest_prediction_at`, `trip_end_parsed_at`, `segmentation_version`, and
`segmented_at`.

## Deployment boundary

The new bundle owns separate replay tables and is not deployed automatically by
this implementation session.

# Canopy segment generation pipeline

Standalone Lakeflow pipeline for finalized-trip mode segmentation.

## Trial architecture

```text
dbw_canopy_trial.sandbox.silver_trip_ended_events
dbw_canopy_trial.sandbox.silver_gps_observations
dbw_canopy_trial.sandbox.silver_mode_predictions
                    |
                    v
          segment generation
                    |
                    v
dbw_canopy_trial.sandbox.silver_mode_segments
```

The pipeline does **not** consume Event Hubs directly. Generic ingestion owns Event Hubs and publishes the validated primitive lifecycle/GPS tables. Mode inference owns pointwise predictions. This repository owns only the finalized-trip segmentation step.

A trip generation is eligible when:

1. a validated `trip_ended` row exists;
2. GPS observations cover `expected_last_sequence`; and
3. every selected GPS event has a pointwise mode prediction.

Incomplete generations simply produce no segment rows on that update. A later triggered update re-evaluates current table snapshots.

## Segmentation behavior

The implementation was extracted from the current trip-finalization sandbox snapshot and preserves its semantics:

- canonicalize duplicate predictions by `event_id`;
- repair short transition-lag returns;
- repair isolated one-point mode islands when adjacent time gaps are bounded;
- assign a new segment whenever stabilized mode changes;
- compute segment distance from internal same-mode GPS edges;
- preserve model name/version lineage.

Boundary edges between two different stabilized modes are deliberately not assigned to either segment. This behavior is preserved from the source implementation and can be revised independently later.

## Trial deployment

The only mutation target is the Trial workspace:

- workspace: `dbw-canopy-trial`
- profile: `CANOPY_TRIAL`
- catalog: `dbw_canopy_trial`
- schema: `sandbox`

Validate and deploy:

```bash
databricks bundle validate -t trial
databricks bundle deploy -t trial
```

Run one triggered update:

```bash
databricks bundle run -t trial segment_generation_pipeline
```

The continuous Job wrapper is deployed paused. Keep it paused during manual smoke tests.

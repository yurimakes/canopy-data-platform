# Canopy Databricks Pipelines

Integrated repository for the Canopy Databricks data/ML path.

## Production bundles

- `pipelines/ingestion`
  - Event Hubs ingestion
  - outputs Bronze events, validated GPS observations, GPS quarantine, and trip-ended events
- `pipelines/inference`
  - stateful GPS feature generation
  - pointwise transportation-mode inference
- `pipelines/segment-generation`
  - finalized-trip readiness checks
  - prediction stabilization and mode-segment generation

Each production bundle remains independently deployable and owns only its own Databricks Job/Pipeline resources.

## Benchmark bundles

- `benchmarks/end-to-segment`
  - creates replay-only Delta inputs
  - generates concurrent synthetic GPS/trip-end events
  - measures trip-end-to-segment latency
  - does not duplicate inference or segmentation logic

The benchmark relies on the replay pipelines owned by the inference and segment-generation bundles.

## Trial environment

- Workspace: `dbw-canopy-trial`
- Catalog: `dbw_canopy_trial`
- Schema: `sandbox`
- CLI profile: `CANOPY_TRIAL`

## Validation

Run each bundle from its own directory:

```bash
cd pipelines/ingestion
databricks bundle validate -t trial

cd ../inference
databricks bundle validate -t trial

cd ../segment-generation
databricks bundle validate -t trial

cd ../../benchmarks/end-to-segment
databricks bundle validate -t trial
```

The three production bundles are intentionally not collapsed into one root Asset Bundle yet. This keeps deployment ownership and failure boundaries explicit while the latency architecture is still being evaluated.

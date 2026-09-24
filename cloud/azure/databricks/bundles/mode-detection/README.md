# Canopy mode detection

This bundle is the replacement path for the latency-sensitive downstream mode-detection runtime.

Current implementation slices:

- defines a model-agnostic `ModeDetectingModel` contract;
- defines the HGBC raw-120 model feature contract;
- computes only the 16 surviving robust HGBC features;
- defines full-window prediction scheduling with a configurable stride;
- defines trip-end tail semantics without partial-window inference;
- runs streaming state, transit-context fusion, and incremental segmentation in one stateful path;
- computes segment distance from the complete contiguous GPS sequence without an intermediate Delta table;
- applies the shared carbon policy at trip seal;
- emits the final durable Gold complete payload directly from the pipeline.

The baseline model is the AI-Hub canonical 120-second HistGradientBoostingClassifier artifact currently maintained in the mobility-model runtime repository.

The five cadence-sensitive canonical fields intentionally excluded from HGBC model input are:

- `point_count`
- `observed_duration_sec`
- `avg_sampling_interval_sec`
- `valid_step_count`
- `gap_step_count`

`valid_point_ratio` remains a model feature. Its denominator is intentionally left as an explicit input for now; its final production source contract will be revisited later.

## Prediction timing

The first prediction is emitted only after a complete 120-second window. Later predictions are emitted on the configured stride, which defaults to 10 seconds but is not hard-coded into processing logic.

Predictions are decisions at their window end. Later overlapping windows do not relabel their entire historical 120-second windows.

At trip end, all stride-aligned predictions due through the final GPS observation must be drained first. If the trip ends between prediction boundaries, the current segment is extended from the last prediction time to the exact trip end. No partial-window terminal prediction is invented.


## Final pipeline boundary

The production-shaped path has no durable mode-detection intermediate table:

```text
Silver GPS + trip_end
        ↓
stateful mode detection
  HGBC → transit fusion → segmentation → distance/carbon/finalization
        ↓
Gold complete_payloads
```

For the sandbox target the sink is
`dbw_canopy_trial.sandbox.jun_016_gold_complete_payloads`.
The former `jun_016_gold_mode_detection_results` table is no longer managed or
written by this bundle.

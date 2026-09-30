# Canopy mode detection

This bundle is the replacement path for the latency-sensitive downstream mode-detection runtime.

Current implementation slices:

- defines a model-agnostic `ModeDetectingModel` contract;
- defines the HGBC raw-120 model feature contract;
- computes only the 16 surviving robust HGBC features;
- defines full-window prediction scheduling with a configurable stride;
- defines trip-end tail semantics without partial-window inference;
- runs streaming state, transit-context fusion, and incremental segmentation in one stateful path;
- computes segment distance from contiguous GPS legs, excluding legs across outages, without an intermediate Delta table;
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

Adjacent GPS points more than `gps_gap_tolerance_seconds` apart (15 seconds by default) create an uncovered outage. The previous mode extends through the last visible GPS point. Inference resumes only after `window_seconds - gps_gap_tolerance_seconds` of post-outage GPS coverage and at the next stride boundary. The first resumed decision labels the observed recovery interval from its first GPS point; it never labels the outage. Outages are not filled from subway context. Cross-outage distance legs are excluded.

At trip end, all stride-aligned predictions due through the final GPS observation must be drained first. An active healthy segment extends to trip end if its tail is shorter than one stride. A trip ending during an outage or unfinished recovery is finalized as partial with uncovered time rather than waiting for more GPS or extending the former mode. No partial-window terminal prediction is invented.

For ordinary windows the transit resolver adds the configurable `context_decision_boost` (default 0.20) to applicable bus/rail evidence for its override decision. Reported raw context scores remain unchanged, and promoting a non-rail model decision to rail still requires the original rail confirmation score.


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


## Optional direct Cosmos sink

The pipeline can fan out the durable Gold stream to Cosmos using Lakeflow
`foreach_batch_sink` + `append_flow`. Gold remains the durable system of
record; the external write is idempotent by `processing_generation` and
`finalization_hash`.

The `sandbox` target enables this direct sink and permits creation of missing
lifecycle documents so Event Hub replay fixtures can exercise the full path.
The normal `trial` target leaves the direct sink disabled by default.

Do not run the separate `cosmos-projection` worker against the same sandbox
while this direct sink is enabled; use the two implementations as A/B variants.

# Canopy mode detection

This bundle is the replacement path for the latency-sensitive downstream mode-detection runtime.

Current implementation slice:

- defines a model-agnostic `ModeDetectingModel` contract;
- defines the HGBC raw-120 model feature contract;
- computes only the 16 surviving robust HGBC features;
- keeps runtime windowing, streaming state, transit-context fusion, segmentation, finalization, and sinks out of scope for this first slice.

The baseline model is the AI-Hub canonical 120-second HistGradientBoostingClassifier artifact currently maintained in the mobility-model runtime repository.

The five cadence-sensitive canonical fields intentionally excluded from HGBC model input are:

- `point_count`
- `observed_duration_sec`
- `avg_sampling_interval_sec`
- `valid_step_count`
- `gap_step_count`

`valid_point_ratio` remains a model feature. Its denominator must represent the raw source point count for the window, not merely the number of validated Silver rows.

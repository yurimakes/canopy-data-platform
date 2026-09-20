# Integrated Mode Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated Lakeflow pipeline that reuses pointwise inference and incrementally emits deterministic finalized mode segments from native Spark state.

**Architecture:** Enrich inference rows internally with GPS coordinates, normalize predictions and trip ends into a tagged union, and group the union by `trip_id` for a `TripSegmentationProcessor`. A pure Python state machine owns ordering, two-stage smoothing, compact segment accumulation, readiness, conflicts, and generation idempotency; the Spark adapter stores its typed state and emits rows to a native streaming table.

**Tech Stack:** Python 3.11+, PySpark 4 `transformWithState`, Lakeflow Declarative Pipelines, Databricks Declarative Automation Bundles, pytest.

**Spec:** `docs/superpowers/specs/integrated-mode-segmentation.md`

## Global Constraints

- Existing inference and segment-generation resources remain unchanged as runnable baselines.
- Public prediction and segment schemas remain compatible.
- Required sequences start at `1`; exact replays are ignored; sequence conflicts fail closed.
- No stream-stream join and no `foreachBatch` sink on the critical output path.
- New tables are isolated replay/sandbox tables.
- Do not deploy automatically.

## Review Focus

- A prediction replay arriving after its point has left the smoothing tail must still be classified as exact or conflicting.
- A trip end arriving before its final prediction must finalize only after the complete contiguous range arrives.
- Conflicting repeated trip ends must never produce output for the affected generation.
- A checkpoint replay after finalization must not emit a generation twice.
- Databricks bundle synchronization must place the shared inference package on the pipeline Python path.

---

### Task 1: Pure incremental segmentation state machine

**Files:**
- Create: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/state_machine.py`
- Create: `pipelines/integrated-mode-segmentation/tests/test_state_machine.py`

**Interfaces:**
- Consumes: normalized `PredictionPoint` and `TripEnd` values.
- Produces: `TripSegmentationState.accept_prediction(point)`, `accept_trip_end(event)`, and `drain_outputs(segmented_at)` returning `SegmentRow` values.

- [ ] Write tests for same-mode trips, transitions, both smoothing patterns, out-of-order arrival, trip-end-before/after-predictions, missing prefixes, Haversine accumulation, processing generation 2, exact replay, conflicting sequence payload, conflicting trip end, and repeated-finalization idempotency.
- [ ] Run `uv run --project pipelines/integrated-mode-segmentation pytest tests/test_state_machine.py -q` and confirm failures are missing-module/API failures.
- [ ] Implement immutable event/output dataclasses and a state machine with sequence fingerprints, pending ordering map, constant-size smoothing tails, segment accumulators, generation metadata, conflict state, and TTL-independent serialization values.
- [ ] Run the focused test file and then the package suite; both must pass.
- [ ] Commit `feat: add incremental trip segmentation state machine`.

### Task 2: Reference parity

**Files:**
- Create: `pipelines/integrated-mode-segmentation/tests/test_reference_parity.py`
- Modify: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/state_machine.py`

**Interfaces:**
- Consumes: Task 1 state-machine API and representative deterministic point sequences.
- Produces: behavior matching the two-pass `stabilize_predictions` and `build_segments` semantics.

- [ ] Add an independent list-based reference implementation of transition-lag repair, singleton repair, and segment construction in the test file; compare all semantic fields and distance tolerance for representative and seeded randomized sequences.
- [ ] Run the parity tests and confirm at least one deliberate edge case fails before any necessary correction.
- [ ] Correct only the state-machine behavior exposed by the failing parity case.
- [ ] Run focused and full package tests; both must pass.
- [ ] Commit `test: prove incremental segmentation parity`.

### Task 3: Spark contracts and state adapter

**Files:**
- Create: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/contracts.py`
- Create: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/events.py`
- Create: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/processor.py`
- Create: `pipelines/integrated-mode-segmentation/tests/test_events.py`
- Create: `pipelines/integrated-mode-segmentation/tests/test_processor.py`

**Interfaces:**
- Consumes: enriched prediction DataFrame, trip-ended DataFrame, and Task 1 state machine.
- Produces: `prediction_events(df)`, `trip_end_events(df)`, `unified_events(predictions, trip_ends)`, `TripSegmentationProcessor`, and `stateful_segment_rows(events, ...)`.

- [ ] Write schema and pure-adapter tests for tagged union projection, row-to-event conversion, state restoration, emitted schema, exact replays, conflicts, and restart idempotency.
- [ ] Run focused tests and confirm missing interfaces fail.
- [ ] Implement union-compatible DDL, segment DDL, native ValueState/MapState-backed processor state, and `transformWithState(..., outputMode="Append", timeMode="ProcessingTime")` wiring.
- [ ] Run focused and full package tests; both must pass.
- [ ] Commit `feat: add native Spark segmentation processor`.

### Task 4: Shared inference enrichment and integrated pipeline

**Files:**
- Modify: `pipelines/inference/mode_inference/contracts.py`
- Modify: `pipelines/inference/mode_inference/state.py`
- Modify: `pipelines/inference/mode_inference/model_inference.py`
- Modify: inference tests covering the internal enriched contract.
- Create: `pipelines/integrated-mode-segmentation/integrated_mode_segmentation/lakeflow_pipeline.py`
- Create: `pipelines/integrated-mode-segmentation/tests/test_pipeline_contract.py`

**Interfaces:**
- Consumes: existing `TripFeatureProcessor`, model loader, Task 3 union and processor.
- Produces: `infer_enriched_predictions(...)`, unchanged `infer_predictions(...)`, inspectable prediction streaming table, and native segment streaming table.

- [ ] Write failing inference tests proving latitude/longitude survive the internal feature path while the public prediction schema stays unchanged; write pipeline contract tests proving one inference path feeds both outputs and no `foreachBatch`/join is present.
- [ ] Run focused tests and confirm the enriched interfaces are absent.
- [ ] Add coordinates to the internal feature schema and factor inference into enriched/public projections without changing `MODE_PREDICTIONS_SCHEMA_DDL`.
- [ ] Implement Lakeflow prediction and segment tables from a shared enriched prediction view plus streamed trip ends.
- [ ] Run inference and integrated suites; both must pass.
- [ ] Commit `feat: integrate inference with stateful segmentation`.

### Task 5: Bundle, documentation, and validation

**Files:**
- Create: `pipelines/integrated-mode-segmentation/databricks.yml`
- Create: `pipelines/integrated-mode-segmentation/resources/integrated_mode_segmentation.replay.pipeline.yml`
- Create: `pipelines/integrated-mode-segmentation/requirements.lakeflow.txt`
- Create: `pipelines/integrated-mode-segmentation/pyproject.toml`
- Create: `pipelines/integrated-mode-segmentation/README.md`
- Create: `pipelines/integrated-mode-segmentation/tests/test_bundle_contract.py`

**Interfaces:**
- Consumes: Task 4 pipeline module and sibling `mode_inference` package.
- Produces: trial-target bundle defining separate integrated prediction and segment tables.

- [ ] Write failing text-contract tests for trial workspace isolation, separate table names, 1-second replay trigger, state TTL, four state partitions, sibling inference synchronization, and absence of deployment side effects.
- [ ] Run the bundle contract tests and confirm missing files fail.
- [ ] Add the self-contained bundle configuration and README covering architecture, state variables, readiness, duplicate/conflict policy, restart semantics, deployment commands, output tables, and limitations.
- [ ] Run all three pipeline unit suites, available Spark tests, `databricks bundle validate -t trial`, and inspect the generated sync/resource plan.
- [ ] Commit `docs: add integrated pipeline bundle and operations guide`.

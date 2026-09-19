# Inference state lifecycle follow-up

Status: **Open**

## Context

The mode inference pipeline keeps one `transformWithState` value per `trip_id`.
Latency benchmarking showed that historical benchmark trips remained in the state
store after they stopped receiving GPS observations:

- current benchmark active trips: 5
- observed `numRowsUpdated`: approximately 5
- observed `numRowsTotal`: 40

Inactive state does not cause the model to re-run old predictions, but retaining
completed trips indefinitely causes unbounded state-store growth and increases
checkpoint, RocksDB, recovery, and operational overhead.

## Temporary decision

Use a **2-hour processing-time TTL** on `trip_feature_state`.

Rationale:

- substantially longer than the expected normal commute duration;
- tolerant of temporary mobile/network gaps;
- prevents abandoned or never-finalized trips from remaining forever;
- simple to apply without introducing a second lifecycle input into the inference
  operator.

The TTL resets whenever the `ValueState` is updated by a newly accepted GPS
observation.

This is a placeholder guardrail, not the intended final lifecycle contract.

## Preferred long-term design

Use the existing `trip_ended` lifecycle event for deterministic cleanup.

Target semantics:

1. GPS observations continue updating per-trip inference state.
2. `trip_ended.expected_last_sequence` identifies the expected terminal GPS
   sequence.
3. Once inference state has reached that sequence, explicitly remove the
   corresponding `trip_id` state.
4. Keep TTL as a fallback for abandoned trips, missing lifecycle events, device
   crashes, or other incomplete sessions.

Do **not** use downstream `mode_segments` as the primary cleanup signal. It is
produced after inference and would create a feedback dependency from segmentation
back into inference.

## Follow-up work

- [ ] Define a unified keyed input contract for GPS observations and lifecycle
      control events.
- [ ] Decide how to handle `trip_ended` arriving before the final GPS row.
- [ ] Implement explicit state removal after
      `last_sequence >= expected_last_sequence`.
- [ ] Retain TTL as fallback after explicit cleanup exists.
- [ ] Measure `numRowsTotal`, state commit latency, and recovery cost under
      realistic long-running load.
- [ ] Revisit the 2-hour TTL using observed commute duration and interruption
      distributions.
- [ ] Document checkpoint/state migration behavior before enabling lifecycle
      changes in production.

## Checkpoint migration note

Two checkpoint-breaking state migrations now exist on this development branch:

1. TTL changed the operator time mode from `NoTime` to `ProcessingTime` and
   wrapped state with TTL metadata.
2. The state representation changed from one JSON `ValueState` to native
   scalar metadata plus bounded point history.
3. The bounded point history then changed from `ListState` to sequence-keyed
   `MapState` so each microbatch mutates only newly added and expired point keys.

Treat both as stateful-query migrations, not ordinary configuration restarts.
Validate against replay first. If Databricks rejects reuse of an existing
checkpoint/state, do not disable schema checking and do not silently reset
production state; establish an explicit reset/migration procedure first.

## Current validation target

After enabling the 2-hour TTL, a short benchmark should preserve the existing
latency behavior. TTL eviction itself cannot be observed in a normal few-minute
benchmark; a targeted short-TTL replay test should be used later to prove that
inactive state is actually removed.

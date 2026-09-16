# mission-policy-v1 20-case simulation

Date: 2026-09-16
Scope: weekly mission selection, adaptive target calculation, profile readiness, assignment idempotency.

## Result

All 20 policy cases pass the executable policy tests. Additional profile and assignment tests also pass.

## Clarifications found during simulation

1. **Zero-car users**: `short_car_share` remains `null` when `car_primary_trip_count=0`, but this null does not force the whole profile to `collecting`. If `car_ratio` is valid and `<= 0.5`, the user can receive `low_carbon_maintain`.
2. **Car-majority users**: if `car_ratio > 0.5` but `short_car_share` is missing, assignment is held as `collecting`; otherwise the short-car vs transit branch would be guessed.
3. **Primary Trip mode**: the current canonical Trip document has segment modes, not a durable Trip-level primary-mode field. v1 derives primary mode only when one mode has a **unique maximum summed segment distance**. A tie is not broken arbitrarily; the Trip is excluded from mission-profile denominators and the invalid reason is retained.
4. **Missing previous same-family result**: if family/target exists but achievement rate is missing, adaptive difficulty restarts at target `1` instead of treating missing data as 0% completion.
5. **Boundary values**: `car_ratio == 0.5` is maintain; `short_car_share == 0.5` is `car_to_transit`. Only strict `> 0.5` enters the majority branch.
6. **Issued assignment is frozen**: one `(campaign_id, user_id, week_start)` produces one deterministic assignment id. Rebuilding the profile or changing policy later in the same week does not replace the stored assignment.
7. **Source-week freshness**: assignment is allowed only when the latest profile's `source_week_end` equals the assignment `week_start`; an older latest profile returns `collecting` rather than silently reusing stale behavior.
8. **No-Trip users**: the current canonical Trip batch has no row from which to enumerate a participant with zero Trips. The API therefore treats a missing latest profile as `collecting`. If an explicit zero-Trip Gold profile row is required, the campaign participant roster must be added as the left-side population source.

## 20 executable cases

| # | Scenario | Expected |
|---|---|---|
| 1 | profile collecting / no valid Trip | collecting |
| 2 | car 0.8, short-car share 0.75 | short_car_to_active, target 1 |
| 3 | car 0.8, short-car share exactly 0.5 | car_to_transit, target 1 |
| 4 | car ratio exactly 0.5 | low_carbon_maintain |
| 5 | both ratios just over 0.5 | short_car_to_active |
| 6 | car over 0.5, short share under 0.5 | car_to_transit |
| 7 | zero car, short share null | low_carbon_maintain |
| 8 | all transit | low_carbon_maintain at observed count |
| 9 | same short-car family, prior 100% | previous target + 1 |
| 10 | same short-car family, partial | target unchanged |
| 11 | same short-car family, 0% | target - 1, min 1 |
| 12 | completed escalation exceeds opportunity | capped at observed opportunity |
| 13 | same transit family, prior 100% | previous target + 1 |
| 14 | transit target 1 then 0% | stays at minimum 1 |
| 15 | previous family differs | new family starts at 1 |
| 16 | maintain family repeated | target equals observed low-carbon count, no +1 escalation |
| 17 | car-majority but short share missing | collecting |
| 18 | short-car opportunity only 1 | escalation capped at 1 |
| 19 | same family but previous achievement missing | restart at target 1 |
| 20 | car ratio 0.5001, short share below 0.5 | car_to_transit |

## Test mapping

- `cloud/azure/functions/func_canopy_dev/tests/test_mission_policy.py`
  - 20-case policy matrix
  - assignment idempotency/freeze
  - stale source-profile rejection
- `cloud/azure/pipelines/databricks/tests/test_build_mission_profile.py`
  - unique-max-distance primary mode
  - primary-mode tie handling
  - short-car and mode count aggregation
  - zero-car nullable share
  - all-ambiguous Trip collecting state

PIPELINE A RUNTIME SMOKE CHECK

## 1. Deployment state

Local `main` was synchronized and is up to date with `origin/main`. No source code was modified. Existing untracked inspection reports were preserved.

Pipeline inspection confirmed:

```text
Pipeline ID:       2a3ca390-4bad-4de4-81e5-98ed584008e1
State:             IDLE
Source:            gps_ingestion/lakeflow_pipeline.py
Channel:           CURRENT
Serverless:        true
Development mode: true
```

The pipeline configuration remains Pipeline A-only. No ML, Gold, feature, segment, prediction, or model-URI configuration has returned.

Bundle state is converged:

```text
Plan: 0 to add, 0 to change, 0 to delete, 1 unchanged
```

## 2. Query execution environment

A one-shot Databricks submit run was used because all SQL warehouses were stopped and were not to be started for this inspection.

```text
Mechanism:          transient serverless notebook task submitted with databricks jobs submit
Submit run ID:      450364164498541
Task run ID:        155960697979845
Performance target: STANDARD
Result:             SUCCESS
Spark version:      4.2.0
Session timezone:   Etc/UTC
Execution time:     130 seconds (196 seconds serverless setup)
```

The task performed only Unity Catalog reads against the three Pipeline A tables. It created no table, schema, saved Job, pipeline update, or data mutation. It did not access Event Hubs or secrets.

Temporary workspace notebook:

```text
/Workspace/Users/user@example.invalid/codex_tmp_pipeline_a_runtime_smoke_20260917
```

The notebook was deleted after the successful run, and a subsequent status lookup confirmed that the path no longer exists. The local temporary script was also removed.

## 3. Bronze results

Table: `dbw_canopy_dev.bronze.gps_events`

```text
Total rows:                    0
Minimum ingested_at:           unavailable (empty table)
Maximum ingested_at:           unavailable (empty table)
Minimum event_hub_enqueued_at: unavailable (empty table)
Maximum event_hub_enqueued_at: unavailable (empty table)
Null body count:               not applicable; no rows
Null ingested_at count:        not applicable; no rows
```

No recent-row sample was available. Consequently, this run cannot demonstrate real raw JSON preservation or populated Event Hubs provenance at row level. The previously validated table schema remains correct.

## 4. Silver observations results

Table: `dbw_canopy_dev.silver.gps_observations`

```text
Total rows:                       0
Distinct trips:                   0
Minimum/maximum event_time:       unavailable (empty table)
Minimum/maximum enqueue time:     unavailable (empty table)
Duplicate event_id groups:        0
Rows in duplicate groups:         0
Required-field null violations:   not applicable; no rows
```

There is no duplicate-output evidence in the currently materialized table, but the empty result does not exercise runtime deduplication with actual events.

## 5. Field integrity

No observation rows were available, so no data-level assertions can be made about `raw_speed`, `vertical_accuracy_m`, `course_deg`, `source`, `quality_flags`, collection metadata, provenance population, or timestamp coherence.

The deployed schema and source still establish that:

- `vertical_accuracy_m` is the public field and stale `vertical_accuracy` is absent;
- `quality_flags` has `ARRAY<STRING>` type;
- all approved provenance and processing-time columns exist;
- `raw_speed` is projected from collector `speed` by the deployed implementation.

These are code/schema confirmations, not observations from live rows.

## 6. Watermark and deduplication

The deployed pipeline configuration reports:

```text
canopy.deduplication_watermark = 1 day
```

The bundle is converged with the deployed pipeline, and current production code performs:

```python
observations.withWatermark(
    "event_hub_enqueued_at", watermark.strip()
).dropDuplicatesWithinWatermark(["event_id"])
```

Confirmed contract:

```text
Watermark column:    event_hub_enqueued_at
Deduplication key:   event_id
Development horizon: 1 day
Guarantee:           bounded deduplication, not permanent global uniqueness
```

`event_time` is not used as the deduplication watermark.

## 7. Quarantine results

Table: `dbw_canopy_dev.silver.gps_quarantine`

```text
Total rows:                  0
Counts by rejection_reason: none
Minimum quarantined_at:      unavailable (empty table)
Maximum quarantined_at:      unavailable (empty table)
Quarantine ratio:            undefined (Bronze row count is zero)
```

No representative row was available to demonstrate retained body, reason-array semantics, or provenance at data level. There is no evidence of duplicates being quarantined.

## 8. Cross-table sanity

```text
Bronze rows:       0
Observation rows:  0
Quarantine rows:   0
```

Because all tables are empty, no row-flow equality or timing-order assertion is appropriate. In particular, no conclusion can be drawn about `event_time`, `received_at`, `bronze_ingested_at`, or `parsed_at` ordering from this run.

The empty state is consistent with the prior full refresh using a fresh checkpoint and `startingOffsets=latest`, followed by no available events during the triggered update.

## 9. Legacy Pipeline B assets

Read-only metadata reconfirmed:

```text
dbw_canopy_dev.silver.gps_features
  pipelines.metastore.inactive = true

dbw_canopy_dev.silver.mode_segments
  pipelines.metastore.inactive = true
```

Neither table was read for row data, refreshed, altered, or otherwise mutated. They remain reserved for future Pipeline B work.

`dbw_canopy_dev.gold.mode_segment_predictions` retained the same table ID, `updated_at`, Delta last-commit timestamp, and Delta version observed before the smoke task. The smoke task did not modify it.

## 10. Final Pipeline A status

**B. PIPELINE A DEPLOYED BUT NO DATA AVAILABLE FOR ROW SMOKE CHECK**

Rationale:

- deployment remains converged and correctly configured;
- the same Pipeline A is IDLE, CURRENT, and serverless;
- the read-only Spark 4.2.0 task successfully accessed all three Unity Catalog tables;
- all three tables contain zero rows;
- no actual input exists to prove raw-body, observation-field, quarantine, timing, or live deduplication behavior;
- no defect or blocking runtime error was observed.

No synthetic traffic should be manufactured merely to change this classification. A future smoke check can be repeated after genuine collector events have arrived and an approved Pipeline A update/orchestration run has processed them.

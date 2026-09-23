PIPELINE A POST-FULL-REFRESH INSPECTION

## 1. Local environment

Working directory: `/home/aletheia/projects/canopy-gps-ingestion`

Local synchronization result:

```text
Branch: main
Local main: up to date with origin/main
Working tree: source unchanged
```

Existing untracked handoff reports were preserved:

```text
codex_pipeline_a_deployment_state.md
codex_pipeline_a_migration_plan.md
```

No virtual environment was needed. No packages were installed. No source changes were made.

## 2. Update 7405c957-f137-41f2-8c5e-48e2aca0ed57

Authoritative `get-update` result:

```text
Pipeline ID:       2a3ca390-4bad-4de4-81e5-98ed584008e1
Update ID:         7405c957-f137-41f2-8c5e-48e2aca0ed57
State:             COMPLETED
Full refresh:      true
Cause:             USER_ACTION
Validate only:     false
Mode:              DEFAULT
Created:           2026-09-16T15:23:19.738Z
Completed:         2026-09-16T15:25:20.590Z (completion event)
Elapsed:           approximately 2 minutes 1 second
Cluster ID:        0916-152321-atbfsxcr-v2n
Serverless:        true
Error:             none
```

The `get-update` response did not populate a separate `completion_time` field; the exact terminal event timestamp above is from the authoritative event log. A Databricks Runtime/Spark version was not exposed in the returned update or runtime event. The pipeline specification confirms serverless execution and channel `CURRENT`.

The event log contains 45 events: all 45 are `INFO`, with no `WARN` or `ERROR` events.

## 3. Pipeline specification

Current pipeline metadata confirms:

```text
Pipeline ID:       2a3ca390-4bad-4de4-81e5-98ed584008e1
State:             IDLE
Latest update:     7405c957-f137-41f2-8c5e-48e2aca0ed57 — COMPLETED
Development mode: true
Serverless:        true
Channel:           CURRENT
Continuous:        not enabled
Catalog:           dbw_canopy_dev
```

Active source library:

```text
/Workspace/Users/user@example.invalid/.bundle/canopy-gps-streaming/dev/files/gps_ingestion/lakeflow_pipeline.py
```

The former `gps_streaming/lakeflow_pipeline.py` source is not configured. There is no pipeline environment/dependency block. The current user configuration contains only Pipeline A table, Event Hubs, UTC timezone, and `1 day` deduplication-watermark settings. It contains no Gold schema/table, model URI, ML, feature-table, segment-table, or prediction-table setting.

Conclusion: the inspected full refresh ran the new Pipeline A definition, not the former combined A/B/C definition.

## 4. Bundle state

Read-only bundle validation:

```text
Validation OK!
```

Bundle summary resolves resource `gps_streaming_pipeline` to the same pipeline ID:

```text
https://adb-7405605578654524.4.azuredatabricks.net/pipelines/2a3ca390-4bad-4de4-81e5-98ed584008e1
```

Current bundle plan:

```text
Plan: 0 to add, 0 to change, 0 to delete, 1 unchanged
```

Therefore, the workspace already contains the merged bundle specification; no bundle deploy is pending or required. The bundle summary lists only the pipeline. A direct read-only lookup confirms obsolete job `287743457610499` no longer exists.

## 5. Pipeline A table schemas

All three objects are Unity Catalog `STREAMING_TABLE` objects owned by `user@example.invalid` and associated with pipeline ID `2a3ca390-4bad-4de4-81e5-98ed584008e1`.

### Bronze

`dbw_canopy_dev.bronze.gps_events` exactly matches the approved contract:

```text
body                    STRING NOT NULL
event_hub_topic         STRING
event_hub_partition     INT
event_hub_offset        BIGINT
event_hub_enqueued_at   TIMESTAMP
ingested_at             TIMESTAMP NOT NULL
```

No missing, extra, renamed, type-incompatible, or nullability-incompatible columns were found.

### Silver observations

`dbw_canopy_dev.silver.gps_observations` exactly matches the approved 25-column contract. In particular:

- `vertical_accuracy_m` is present and nullable;
- stale `vertical_accuracy` is absent;
- `raw_speed`, `course_deg`, `source`, `quality_flags`, `collection_mode`, and `label` have the approved names and types;
- all four Event Hubs provenance fields are present;
- required fields, including `quality_flags`, are non-nullable;
- `event_hub_enqueued_at` is present for bounded ingestion deduplication.

No schema mismatch was found.

### Silver quarantine

`dbw_canopy_dev.silver.gps_quarantine` exactly matches the approved 11-column contract, including nullable best-effort `schema_version`/`event_id`, non-null `rejection_reason`, non-null `ARRAY<STRING>` `rejection_reasons`, provenance, and non-null processing timestamps.

No schema mismatch was found.

All three catalog objects retained their existing top-level table IDs while their pipeline-managed backing tables/state were reset. This is consistent with an in-place Lakeflow full refresh rather than creation of a second public table set.

## 6. Former B/C tables

Both former outputs still exist as pipeline-owned streaming tables but are inactive:

```text
dbw_canopy_dev.silver.gps_features
  pipeline ID: 2a3ca390-4bad-4de4-81e5-98ed584008e1
  pipelines.metastore.inactive: true

dbw_canopy_dev.silver.mode_segments
  pipeline ID: 2a3ca390-4bad-4de4-81e5-98ed584008e1
  pipelines.metastore.inactive: true
```

The inspected update itself marked both inactive at graph setup:

```text
2026-09-16T15:24:41.847Z — mode_segments marked inactive
2026-09-16T15:24:42.242Z — gps_features marked inactive
```

They were metadata-modified during this update to record inactivity, but no flow for either dataset was defined or run. The event messages explicitly state that the pipeline will no longer update them.

The update also marked the former private table `canopy_gps_stateful_output` inactive. It is not part of the new graph and can be considered during later separately approved legacy cleanup.

`dbw_canopy_dev.gold.mode_segment_predictions` remains a standalone managed Delta table with no pipeline ID. Its catalog `updated_at`, Delta last-commit timestamp, and last update version all predate update `7405c957-f137-41f2-8c5e-48e2aca0ed57`. No event in this update references Gold. It was not modified by the update.

No tables were dropped during this inspection.

## 7. Event Hubs ingestion/runtime result

Event Hubs source initialization succeeded at the level observable without reading secrets or starting SQL compute:

- the Bronze source flow progressed through `STARTING`, `RUNNING`, streaming-update completion, and `COMPLETED`;
- the parsed, observations, and quarantine flows all completed afterward;
- the entire update completed successfully;
- there were no Kafka, Event Hubs, secret, authentication, checkpoint, or source errors in the 45 update events.

This is affirmative evidence that authentication and Kafka/Event Hubs source initialization worked for this update.

Whether Bronze ingested a nonzero number of payload records cannot be established from the returned metadata/event records: the API events contain no row/source metrics, and Unity Catalog metadata exposes no current row-count statistic for these streaming tables. Both available SQL warehouses were stopped. In accordance with the task constraint, no warehouse was started merely to count or sample rows.

Accordingly:

```text
Event Hubs source/auth initialization: successful
Streaming flow execution:              successful
Bronze nonzero row intake:              unknown
Observations nonzero rows:              unknown
Quarantine nonzero rows:                unknown
```

No secrets were retrieved or printed, and no synthetic events were produced.

## 8. Relevant pipeline events

Relevant chronological events for the authoritative update:

```text
15:23:19.738Z  Update started by USER_ACTION
15:23:21.430Z  WAITING_FOR_RESOURCES
15:23:49.109Z  INITIALIZING
15:24:20.785Z  RESETTING
15:24:22.298Z  gps_quarantine successfully reset
15:24:22.300Z  gps_events successfully reset
15:24:22.374Z  gps_observations successfully reset
15:24:22.519Z  SETTING_UP_TABLES
15:24:22.924Z  new private gps_events_parsed table created
15:24:41.406Z  Bronze APPEND flow defined
15:24:41.465Z  private parsed APPEND flow defined
15:24:41.482Z  quarantine APPEND flow defined
15:24:41.488Z  observations APPEND flow defined
15:24:41.847Z  mode_segments marked inactive
15:24:42.047Z  former private stateful output marked inactive
15:24:42.242Z  gps_features marked inactive
15:24:42.256Z  RUNNING
15:24:53.522Z  Bronze flow COMPLETED
15:25:01.767Z  private parsed flow COMPLETED
15:25:05.535Z  quarantine flow COMPLETED
15:25:20.492Z  observations flow COMPLETED
15:25:20.590Z  update COMPLETED
```

No schema incompatibility, expectation failure, quarantine warning, authentication failure, Kafka error, or other warning/error was emitted.

## 9. Current state category

**A. Full refresh succeeded on the new Pipeline A definition.**

Evidence:

- update `7405c957-f137-41f2-8c5e-48e2aca0ed57` is `COMPLETED` and `full_refresh=true`;
- its captured configuration uses CURRENT, the `1 day` watermark, and `gps_ingestion/lakeflow_pipeline.py`;
- all three A tables were explicitly reset and now match the approved contracts exactly;
- the new private parsed dataset was created and completed;
- only the four new graph flows were defined and completed;
- former B/C outputs were marked inactive, not run;
- bundle plan is fully converged with zero pending actions;
- the pipeline is now `IDLE`, as expected for a successfully completed triggered update.

## 10. Recommended next action

No corrective deployment, normal update, or additional full refresh is required. Do not run another full refresh.

The exact next operational action should be a separately approved observation/activation decision:

1. If producer traffic is expected, use an already-running approved query facility or the next approved pipeline run to confirm nonzero Bronze/observations/quarantine counts and inspect only a minimal sample. The present inspection proves source initialization, not nonzero traffic.
2. After that runtime smoke check, introduce and deploy a new continuous orchestration job only if continuous ingestion is desired. The pipeline itself is currently triggered/non-continuous and IDLE, and the old job has been removed.
3. Later, under separate approval, drop inactive `gps_features`, `mode_segments`, and the inactive private stateful artifact if their data is no longer needed.
4. Leave `gold.mode_segment_predictions` untouched.

Current deployment assessment: Pipeline A is correctly deployed and its first clean full-refresh update succeeded. The only unresolved runtime fact is whether any Event Hubs records were available during that short triggered update.

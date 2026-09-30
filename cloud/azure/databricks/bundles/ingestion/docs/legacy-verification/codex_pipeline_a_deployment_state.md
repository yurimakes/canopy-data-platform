DEPLOYMENT STATE INSPECTION

## 1. Repository state

- Repository: `/home/aletheia/projects/canopy-gps-ingestion`
- Branch: `main`
- HEAD: `e5f6e1a` (`Merge pull request #2 from aletheia-ops/fix/pipeline-a-spark-validation`)
- `main` was fast-forwarded from `f094ac1` to `e5f6e1a` and is synchronized with `origin/main`.
- The merged Spark 4 compatibility commit `679547a` is present through PR #2.
- `databricks bundle validate --profile CANOPY_DEV -t dev`: **PASS** (`Validation OK!`).
- The worktree was clean before this required report was created.
- No source changes were required. This report is the only local file added by the inspection.

## 2. Configured deployment identity

Repository configuration:

| Item | Configured value |
|---|---|
| Bundle name | `canopy-gps-streaming` |
| Target | `dev` (default target) |
| Target mode | `development` |
| Pipeline resource key | `gps_streaming_pipeline` |
| Pipeline resource name | `canopy-gps-streaming-pipeline-dev` before development-mode display prefixing |
| Catalog | `dbw_canopy_dev` |
| Pipeline default schema | `silver` |
| Bronze schema | `bronze` |
| Silver schema | `silver` |
| Serverless | `true` |
| Channel | `CURRENT` |
| Continuous | not configured |
| Workspace host | `https://adb-7405605578654524.4.azuredatabricks.net` |
| Workspace root | `/Workspace/Users/user@example.invalid/.bundle/canopy-gps-streaming/dev` |
| Resolved source path | `/Workspace/Users/user@example.invalid/.bundle/canopy-gps-streaming/dev/files/gps_ingestion/lakeflow_pipeline.py` |

The deployed bundle metadata at the same workspace root binds resource key `gps_streaming_pipeline` to pipeline ID `2a3ca390-4bad-4de4-81e5-98ed584008e1`. Bundle name, target, workspace root, and resource key match the new repository, so the configured resource corresponds to an existing pipeline rather than a new unbound resource.

The metadata itself is from the former monorepo deployment (`aletheia-ops/canopy-data-platform`, branch `feature/gps-databricks-integration`, commit `1ab5af532018dd9e734c6f6d4553aa8217182d86`). It also binds an old job resource named `gps_streaming` to job ID `287743457610499`.

## 3. Existing Databricks pipeline state

- Pipeline ID: `2a3ca390-4bad-4de4-81e5-98ed584008e1`
- Display name: `[dev 5dt016] canopy-gps-streaming-pipeline-dev`
- State: `IDLE`
- Development mode: `true`
- Serverless: `true` (effective serverless compute ID `aa7d5738-29a4-3d1d-bf11-6456eac675d7`)
- Deployed channel: `PREVIEW`
- Continuous mode: `false`
- Catalog/schema: `dbw_canopy_dev` / `silver`
- Publishing mode: `DEFAULT_PUBLISHING_MODE`
- Runtime/DBR version: not exposed by the pipeline metadata API.
- Latest recorded action: validation-only update `fe27346c-04f5-494d-bcbe-f8f00bb11005`, created `2026-09-16T10:39:12.811Z`, state `COMPLETED`.
- Latest non-validation update: `212495d3-f6ff-4d6f-9e39-a40dbf7041fc`, created `2026-09-15T12:49:25.407Z`, state `COMPLETED`, `full_refresh=false`.

The deployed library still points to:

```text
/Workspace/Users/user@example.invalid/.bundle/canopy-gps-streaming/dev/files/gps_streaming/lakeflow_pipeline.py
```

Its environment loads `gps_streaming/requirements.lakeflow.txt`, containing `mlflow`, `torch`, `numpy`, `pandas`, `scikit-learn`, and `joblib`. Read-only source inspection found `transformWithState`, `gps_features`, `mode_segments`, and bounded SpeedTransformer inference. Its configuration also contains Gold/ML schema, features/segments/predictions tables, and a model URI. It is therefore conclusively the former combined Pipeline A/B/C deployment.

The merged repository intends to replace that source with `gps_ingestion/lakeflow_pipeline.py`, remove ML dependencies and downstream tables, and move from `PREVIEW` to `CURRENT` while preserving the same pipeline identity.

## 4. Active writers

No writer is active at inspection time:

- Pipeline `2a3ca390-4bad-4de4-81e5-98ed584008e1` is `IDLE`.
- Bound job `287743457610499` (`[dev 5dt016] canopy-gps-streaming-dev`) is a continuous job whose only task invokes that pipeline; its `pause_status` is `PAUSED`.
- `databricks jobs list-runs --active-only` returned no active runs.
- The only other visible pipeline and jobs belong to unrelated weekly-analysis and trip-finalization workloads; their configurations do not reference the Pipeline A pipeline or its tables.

Unity Catalog identifies pipeline `2a3ca390-4bad-4de4-81e5-98ed584008e1` as the owner/writer for all five streaming tables below:

- `dbw_canopy_dev.bronze.gps_events`
- `dbw_canopy_dev.silver.gps_observations`
- `dbw_canopy_dev.silver.gps_quarantine`
- `dbw_canopy_dev.silver.gps_features`
- `dbw_canopy_dev.silver.mode_segments`

Thus there is one registered Lakeflow writer for each intended Pipeline A table today, but it is the old combined writer. The one-writer rule remains safe only if the new bundle updates this bound pipeline ID in place and the old continuous job cannot independently reactivate an old configuration. No exhaustive guarantee can be made about ad hoc notebook/API writers from catalog metadata alone, although no active job run or second pipeline ownership was found.

The former Gold table `dbw_canopy_dev.gold.mode_segment_predictions` also exists as a managed Delta table. It has no `pipelines.pipelineId` property; the deployed combined source shows it was written as an inference side effect rather than a declarative pipeline table.

## 5. Existing Pipeline A tables

Row counts were omitted. The Unity Catalog metadata for these streaming tables contains no safe row-count statistic, and both available SQL warehouses were `STOPPED`; none was started for this inspection.

### `dbw_canopy_dev.bronze.gps_events`

- Exists: yes
- Table ID: `b13f6532-e6ed-410e-a1ab-261163c17d17`
- Type: `STREAMING_TABLE`
- Owner: `user@example.invalid`
- Pipeline owner: `2a3ca390-4bad-4de4-81e5-98ed584008e1`
- Storage/provider: the API does not expose `data_source_format`; properties show a pipeline-managed backing table in managed Unity Catalog storage, not an external table.
- Current schema: `body STRING`, `event_hub_topic STRING`, `event_hub_partition INT`, `event_hub_offset BIGINT`, `event_hub_enqueued_at TIMESTAMP`, `ingested_at TIMESTAMP`; every column is reported nullable.

### `dbw_canopy_dev.silver.gps_observations`

- Exists: yes
- Table ID: `1fc9703a-0a72-476d-a6ef-e0204175b39b`
- Type: `STREAMING_TABLE`
- Owner: `user@example.invalid`
- Pipeline owner: `2a3ca390-4bad-4de4-81e5-98ed584008e1`
- Storage/provider: pipeline-managed backing table in managed Unity Catalog storage; provider is not separately exposed.
- Current schema, in order: `schema_version STRING`, `event_id STRING`, `user_id STRING`, `device_id STRING`, `trip_id STRING`, `sequence BIGINT`, `event_time TIMESTAMP`, `received_at TIMESTAMP`, `lat DOUBLE`, `lon DOUBLE`, `accuracy DOUBLE`, `raw_speed DOUBLE`, `altitude_m DOUBLE`, `vertical_accuracy DOUBLE`, `event_hub_enqueued_at TIMESTAMP`, `bronze_ingested_at TIMESTAMP`, `parsed_at TIMESTAMP`; every column is reported nullable.
- `event_time` carries persisted watermark metadata of `600000` ms (10 minutes), matching the stale deployed parser.

### `dbw_canopy_dev.silver.gps_quarantine`

- Exists: yes
- Table ID: `2f4347a2-b3fd-4b75-a138-d4191eba82d0`
- Type: `STREAMING_TABLE`
- Owner: `user@example.invalid`
- Pipeline owner: `2a3ca390-4bad-4de4-81e5-98ed584008e1`
- Storage/provider: pipeline-managed backing table in managed Unity Catalog storage; provider is not separately exposed.
- Current schema, in order: `body STRING`, `rejection_reason STRING`, `event_hub_enqueued_at TIMESTAMP`, `bronze_ingested_at TIMESTAMP`, `quarantined_at TIMESTAMP`; every column is reported nullable.

Relevant former outputs also exist as pipeline-owned `STREAMING_TABLE`s: `silver.gps_features` and `silver.mode_segments`. The feature table contains derived distance/speed/transition fields, but those columns do not appear inside the three Pipeline A public tables. `gold.mode_segment_predictions` exists separately as a managed Delta table.

## 6. Schema compatibility

### Bronze

- Missing columns: none.
- Extra columns: none.
- Type differences: none.
- Nullability differences: deployed `body` and `ingested_at` are nullable; the approved contract requires both `NOT NULL`.
- Assessment: structurally close, but not contract-compatible on nullability.

### Silver observations

- Missing columns: `vertical_accuracy_m`, `course_deg`, `source`, `quality_flags`, `collection_mode`, `label`, `event_hub_topic`, `event_hub_partition`, `event_hub_offset`.
- Extra/stale column: `vertical_accuracy`.
- Rename required: stale `vertical_accuracy` must not be treated as an alias; the approved column is `vertical_accuracy_m`.
- Existing column types: compatible with the approved types.
- Nullability differences: all deployed columns are nullable. Among present columns, the approved contract requires `schema_version`, `event_id`, `user_id`, `device_id`, `trip_id`, `sequence`, `event_time`, `received_at`, `lat`, `lon`, `bronze_ingested_at`, and `parsed_at` to be `NOT NULL`. The missing `source` and `quality_flags` are also required `NOT NULL` in the approved contract.
- Stateful semantics difference: the deployed table records a 10-minute watermark on `event_time`; the new contract deduplicates by `event_id` with configurable bounded state using `event_hub_enqueued_at` (development default `1 day`).
- Derived/detector columns: none are present in `gps_observations`; they live in the separate old `gps_features` and `mode_segments` tables.

### Silver quarantine

- Missing columns: `schema_version`, `event_id`, `rejection_reasons`, `event_hub_topic`, `event_hub_partition`, `event_hub_offset`.
- Extra columns: none.
- Existing column types: compatible with the approved types.
- Nullability differences: deployed `body`, `rejection_reason`, `bronze_ingested_at`, and `quarantined_at` are nullable but must be `NOT NULL`; missing `rejection_reasons` must also be `ARRAY<STRING> NOT NULL`.
- Assessment: materially incompatible with the approved diagnostic/replay contract.

## 7. Existing data compatibility

No Bronze payload sample was read. Both SQL warehouses were stopped, and starting one would change resource state; the table APIs expose schema/ownership but not payload values. A small sample therefore was not safely available under the stated restrictions.

Read-only inspection of the deployed parser establishes migration risk but not the actual payload distribution:

- It uses typed `from_json`.
- It accepts only `canopy.gps.collector.v0.1`.
- It parses/projects `vertical_accuracy`, not authoritative `vertical_accuracy_m`.
- It uses `event_time` with a 10-minute watermark and `event_id` deduplication.
- The current Silver schema contains `vertical_accuracy`, corroborating execution of the stale contract.

It remains unknown whether retained Bronze rows contain only stale v0.1/`vertical_accuracy`, authoritative v0.1/`vertical_accuracy_m`, v0.2, or a mixture. If existing Bronze/checkpoint state is preserved, strict `_m` validation may send stale payloads to quarantine; if tables are recreated, retained replay/debug data will be lost unless separately preserved through an approved migration.

## 8. Event Hubs consumer-group risk

- Repository consumer group: `canopy-databricks`.
- Deployed combined pipeline consumer group: `canopy-databricks`.
- Namespace/topic also match: `evhns-canopy-dev` / `evh-canopy-gps-dev`.
- The SAS secret was not read; only configuration names were inspected.

There is no current competition because the pipeline is IDLE, its continuous orchestration job is PAUSED, and no job run is active. Updating the bound pipeline ID in place should preserve a single Databricks consumer identity. Creating a second pipeline, losing the bundle binding, or reactivating the old orchestration while another consumer is running would put two consumers in the same group and can cause partition rebalancing/competing consumption. Activation must therefore be serialized and the old orchestration disposition made explicit.

## 9. Recommended migration/deployment path

**Selected category: C — Development tables should be recreated before new Pipeline A activation.**

Rationale:

- This is not category D or E: the current bundle identity and resource key are already bound to the existing pipeline ID.
- An in-place pipeline configuration update is identity-compatible, but its existing public streaming tables are not schema-compatible.
- Observations requires a strict field replacement (`vertical_accuracy` to `vertical_accuracy_m`), nine missing columns, NOT NULL enforcement, and a watermark-column/retention change.
- Quarantine requires six missing columns and stronger nullability.
- Bronze requires NOT NULL enforcement and its retained payload compatibility is unknown.
- Relying on automatic Lakeflow evolution for column removal/rename, nullability tightening, and stateful watermark changes is unsafe. A planned development-table recreation/reset is clearer and lower risk than attempting implicit evolution.

Recommended later, explicitly approved sequence:

1. Decide whether existing Bronze data must be sampled/exported/preserved before destructive work.
2. Confirm the bundle remains bound to pipeline ID `2a3ca390-4bad-4de4-81e5-98ed584008e1`; do not create a second pipeline.
3. Approve and perform an explicit recreation/reset strategy for the three Pipeline A streaming tables and their pipeline state.
4. Decide ownership/retention for old `gps_features`, `mode_segments`, and `mode_segment_predictions`; they are outside Pipeline A.
5. Retire or deliberately replace the paused old continuous job before activation.
6. Deploy the clean Pipeline A definition, validate the resulting graph/schema, then activate only after confirming no competing consumer.

No migration, reset, deployment, or activation was performed during this inspection.

## 10. Blocking issues before deployment

### Blocking (2)

1. **Public table contracts are incompatible.** An explicit, approved schema migration/recreation plan is required for all three intended tables; observations and quarantine cannot safely be assumed to evolve automatically, and Bronze nullability also differs.
2. **The former combined deployment must be retired deliberately.** The same pipeline still owns Pipeline B/C streaming tables, loads ML dependencies, and is referenced by a paused continuous job. The future deploy must preserve the pipeline binding while explicitly handling removal of the old job and downstream table ownership before any activation.

### Non-blocking

- Bundle validation succeeds.
- The configured bundle/resource identity matches the deployed pipeline ID.
- The pipeline is IDLE, the old continuous job is PAUSED, and no active job runs were found.
- Serverless remains enabled; moving from deployed `PREVIEW` to repository `CURRENT` is an intentional configuration update.
- No derived-feature/detector columns were found inside the three Pipeline A public tables themselves.

### Unknown / requires approval

- Existing Bronze payload version/field distribution was not sampled; preservation versus recreation/replay requires an explicit data-retention decision.
- Catalog/job metadata cannot rule out every ad hoc notebook or external API writer, although no second pipeline owner or active job was found.
- The precise future bundle deployment plan for deleting the no-longer-declared old job was not executed because only validation and read-only inspection were authorized.
- Disposition of `silver.gps_features`, `silver.mode_segments`, and `gold.mode_segment_predictions` requires owner approval because they are outside Pipeline A but remain from the combined deployment.

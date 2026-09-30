PIPELINE A MIGRATION PLAN — PATH R

## 1. Current state confirmation

Bronze retention choice: Path R — old development Bronze data will not be preserved.

Repository synchronization completed on `main`:

```text
Already on 'main'
Your branch is up to date with 'origin/main'.
Already up to date.
```

The repository contains an unrelated, previously generated untracked report, `codex_pipeline_a_deployment_state.md`. It was left untouched. No source changes were required.

Confirmed current Databricks state:

- Pipeline ID: `2a3ca390-4bad-4de4-81e5-98ed584008e1`
- Deployed name: `[dev 5dt016] canopy-gps-streaming-pipeline-dev`
- State: `IDLE`
- Development mode: enabled
- Serverless: enabled
- Deployed channel: `PREVIEW`
- Continuous pipeline mode: disabled
- Deployed implementation: former combined Pipeline A/B/C
- Legacy orchestration job: `287743457610499`, paused, with no active runs found

The legacy deployment owns the three Pipeline A tables plus `silver.gps_features` and `silver.mode_segments`. The three Pipeline A tables require clean recreation because their schemas and/or streaming state are incompatible with the merged implementation. `gold.mode_segment_predictions` is outside this pipeline and must remain untouched.

## 2. Bundle identity and deployment impact

### Configured identity

The merged repository configures:

```text
Bundle name:          canopy-gps-streaming
Target:               dev
Target mode:          development
Workspace host:       https://adb-7405605578654524.4.azuredatabricks.net
CLI profile:          CANOPY_DEV
Workspace root:       /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}
Pipeline resource:    gps_streaming_pipeline
Pipeline name:        canopy-gps-streaming-pipeline-${bundle.target}
Catalog:              dbw_canopy_dev
Default schema:       silver
Bronze schema:        bronze
Silver schema:        silver
Pipeline source:      ${workspace.file_path}/gps_ingestion/lakeflow_pipeline.py
Channel:              CURRENT
Serverless:           true
Continuous:           not declared
```

The synchronized bundle deployment metadata binds `gps_streaming_pipeline` to existing pipeline ID `2a3ca390-4bad-4de4-81e5-98ed584008e1`. `databricks bundle summary --force-pull` displayed that exact pipeline URL and the legacy job ID.

### Read-only deployment plan result

The following supported read-only plan was executed:

```bash
databricks bundle plan --profile CANOPY_DEV -t dev
```

Result:

```text
delete jobs.gps_streaming
update pipelines.gps_streaming_pipeline
Plan: 0 to add, 1 to change, 1 to delete, 0 unchanged
```

The JSON plan further confirms that deployment is expected to:

- update pipeline ID `2a3ca390-4bad-4de4-81e5-98ed584008e1` in place;
- replace the old `gps_streaming/lakeflow_pipeline.py` library with `gps_ingestion/lakeflow_pipeline.py`;
- remove the old ML dependency environment;
- remove Gold, ML, feature, segment, prediction, and model-URI configuration;
- add the `1 day` ingestion deduplication watermark and UTC timezone settings;
- change channel `PREVIEW` to `CURRENT`;
- delete bundle-managed job `287743457610499` because it is absent from the new bundle;
- leave unrelated workspace resources, including `gold.mode_segment_predictions`, outside the plan.

Therefore, `databricks bundle deploy` should update the existing pipeline rather than create a second one. The present risk of a second pipeline is low, but stale or replaced bundle state immediately before deployment could change that conclusion.

Mandatory safeguard immediately before approval: rerun both commands below and require the same pipeline URL/ID, `0 to add`, exactly one pipeline update, and exactly one deletion for job `287743457610499`:

```bash
databricks bundle summary --profile CANOPY_DEV -t dev --force-pull
databricks bundle plan --profile CANOPY_DEV -t dev --output json
```

Abort if the plan contains a pipeline create, a different pipeline ID, any Gold action, or any unrelated deletion.

### Separation of effects

- Bundle deployment synchronizes workspace files and changes the pipeline specification. It also removes the obsolete bundle-managed job. It does not itself run the pipeline, consume Event Hubs, rebuild tables, or analyze removed dataset definitions through a pipeline update.
- The first pipeline update evaluates the new source graph. At that point removed B/C datasets become inactive, and the current A graph is instantiated.
- A full-refresh update additionally clears managed streaming-table data and checkpoint state, rebuilds the graph, and starts processing. It is both destructive reset and activation; it is not a passive metadata operation.

## 3. Former B/C dataset behavior

The merged source no longer declares:

```text
dbw_canopy_dev.silver.gps_features
dbw_canopy_dev.silver.mode_segments
```

Current Lakeflow behavior is not automatic deletion by default. On the next pipeline update, a previously defined streaming table that disappears from the source is marked **inactive**. It remains queryable but is no longer updated. The repository does not set `pipelines.dropInactiveTables=true`, so neither table should be auto-dropped. Databricks documents this inactive-dataset lifecycle and requires explicit cleanup when automatic inactive-table deletion is disabled: [Use Unity Catalog with Lakeflow Declarative Pipelines](https://docs.databricks.com/aws/en/ldp/unity-catalog).

Recommended retirement procedure after the new update succeeds:

1. Verify from pipeline details/event logs that both datasets are inactive and receive no writes.
2. Verify their exact names and that neither has acquired an independent writer.
3. With separate explicit approval, run:

   ```sql
   DROP TABLE dbw_canopy_dev.silver.gps_features;
   DROP TABLE dbw_canopy_dev.silver.mode_segments;
   ```

4. Retain the operation record. Unity Catalog managed tables can normally be recovered with `UNDROP TABLE` during the documented recovery window, but that recovery window must not be treated as a substitute for the pre-drop checks.

The bundle deployment alone will not drop these tables. `gold.mode_segment_predictions` is neither declared nor targeted by this bundle and must not be included in cleanup.

## 4. Pipeline A clean-reset strategy

### Option assessment

- Normal update: insufficient. It would retain incompatible table data and streaming checkpoints.
- Checkpoint reset only: insufficient. Resetting a checkpoint while retaining old table data does not cleanly replace incompatible schemas or remove old rows.
- Selective full refresh: technically possible, but unnecessary complexity here. All three public A tables and the private parsed/validated dataset belong to the changed graph and should start cleanly.
- Manual `DROP TABLE`: avoid for the A tables. It adds Unity Catalog lifecycle work that Lakeflow can perform consistently itself.
- Full pipeline refresh: preferred. Databricks documents that full refresh clears streaming-table data and checkpoint state and restarts the flows. It is appropriate for renamed or hard-deleted columns and changes to stateful/deduplication logic: [Full refresh for streaming tables](https://docs.databricks.com/aws/en/ldp/full-refresh-st), [How pipeline refresh works](https://docs.databricks.com/aws/en/ldp/concepts/refresh).

### Exact recommendation

After the in-place bundle deployment and final identity checks, perform one full-refresh update of pipeline `2a3ca390-4bad-4de4-81e5-98ed584008e1`.

That operation must rebuild:

- `bronze.gps_events`: discard old rows and checkpoint, then create the approved non-null raw-body contract from the new source graph;
- `silver.gps_observations`: discard the stale `vertical_accuracy` schema, old `event_time` watermark, prior rows, and prior deduplication state; rebuild with `vertical_accuracy_m`, operational provenance, and bounded `event_id` deduplication on `event_hub_enqueued_at`;
- `silver.gps_quarantine`: discard old rows and incompatible schema; rebuild with the full reasons array and provenance;
- the private parsed/validated dataset and its flow state.

No separate `DROP TABLE` is recommended for these three tables. No archive is required. Old A-table contents and checkpoints become unrecoverable under the approved Path R policy.

## 5. Event Hubs behavior after reset

The production source specifies:

```text
startingOffsets = latest
consumer group = canopy-databricks
```

Spark applies `startingOffsets` only when a streaming query has no usable checkpoint. When a checkpoint exists, Spark resumes from checkpointed source offsets. Spark Structured Streaming tracks offsets in its checkpoint rather than using Kafka consumer-group committed offsets as its recovery position. Spark also warns that forcing the same Kafka group ID across concurrent queries can cause consumer interference: [Spark Structured Streaming Kafka integration](https://spark.apache.org/docs/3.5.6/structured-streaming-kafka-integration.html).

Consequently, after the approved full refresh removes the old Lakeflow checkpoint:

- each Event Hubs partition initializes at its latest offset when the new query starts;
- retained historical events before those captured latest offsets are not replayed;
- events at or after initialization are eligible for ingestion;
- consumer-group committed offsets do not override `startingOffsets=latest` for the fresh Spark query;
- a simultaneous old consumer using `canopy-databricks` would still pose partition-assignment/interference risk even though it would not supply Spark recovery offsets.

This matches the migration intent to discard old development state and begin with new/current events. No source configuration change is required. The precise boundary is the per-partition latest offset captured at query initialization, not the wall-clock instant at which the CLI command is issued.

The old job is paused and has no active runs; bundle deployment removes it before activation. Immediately before activation, verify again that no active job or pipeline update uses the same consumer group.

## 6. Exact deployment runbook

### Phase A — preflight (read-only)

Run from `/home/aletheia/projects/canopy-gps-ingestion`:

```bash
git switch main
git pull
git status --short --branch
databricks bundle validate --profile CANOPY_DEV -t dev
databricks bundle summary --profile CANOPY_DEV -t dev --force-pull
databricks bundle plan --profile CANOPY_DEV -t dev
databricks bundle plan --profile CANOPY_DEV -t dev --output json
databricks pipelines get 2a3ca390-4bad-4de4-81e5-98ed584008e1 --profile CANOPY_DEV --output json
databricks jobs get 287743457610499 --profile CANOPY_DEV --output json
databricks jobs list-runs --active-only --profile CANOPY_DEV --output json
```

Acceptance gates:

- local `main` is synchronized and source files are unmodified;
- bundle validation succeeds;
- summary binds `gps_streaming_pipeline` to exactly `2a3ca390-4bad-4de4-81e5-98ed584008e1`;
- plan is exactly `0 add / 1 pipeline update / 1 old-job delete`;
- the pipeline is `IDLE`;
- old job `287743457610499` is paused and has no active runs;
- no other active run targets this pipeline or the shared Event Hubs consumer group;
- the plan contains no Gold resource and no unrelated resource action.

### Phase B — deploy code/configuration

`REQUIRES EXPLICIT APPROVAL`

```bash
databricks bundle deploy --profile CANOPY_DEV -t dev --fail-on-active-runs
```

Expected effects: upload/synchronize the merged Pipeline A files, update the same pipeline ID to the CURRENT/no-ML/A-only specification, and delete bundle-managed job `287743457610499`. It must not run the pipeline or change tables. Do not use `--auto-approve`; review the deletion confirmation.

Immediately afterward, use read-only `bundle summary`, `bundle plan`, `pipelines get`, and `jobs get` to confirm the same pipeline ID, the new source path, CURRENT channel, absent ML environment/configuration, and deletion of the legacy job. The plan should then report no pending changes. The existing A-table schemas are expected to remain old until the full refresh.

### Phase C — clean reset/recreation

There is no separate recommended reset-only command. The supported full refresh is the clean reset and first update in one operation.

`REQUIRES EXPLICIT APPROVAL — DESTRUCTIVE AND ACTIVATES EVENT HUBS CONSUMPTION`

```bash
databricks pipelines start-update 2a3ca390-4bad-4de4-81e5-98ed584008e1 --full-refresh --cause USER_ACTION --profile CANOPY_DEV --output json
```

Expected effect: destroy old data/checkpoints for the pipeline-managed streaming graph, recreate the three A public tables and private dataset from the new definition, and start the update. Capture the returned update ID. Do not precede this with manual A-table drops.

### Phase D — validate the resulting pipeline

Before Phase C, read-only inspection can validate the deployed specification but cannot validate runtime graph construction or resulting table schemas. Avoid a separate `--validate-only` update because the pipeline source resolves Event Hubs authentication during graph construction; it would be an additional pipeline operation and may access the secret.

After the approved full-refresh update, verify:

```bash
databricks pipelines get 2a3ca390-4bad-4de4-81e5-98ed584008e1 --profile CANOPY_DEV --output json
databricks pipelines get-update 2a3ca390-4bad-4de4-81e5-98ed584008e1 <UPDATE_ID> --profile CANOPY_DEV --output json
databricks tables get dbw_canopy_dev.bronze.gps_events --profile CANOPY_DEV --output json
databricks tables get dbw_canopy_dev.silver.gps_observations --profile CANOPY_DEV --output json
databricks tables get dbw_canopy_dev.silver.gps_quarantine --profile CANOPY_DEV --output json
```

Acceptance gates:

- pipeline ID remains unchanged;
- library is `gps_ingestion/lakeflow_pipeline.py`;
- channel is CURRENT and no ML environment/configuration remains;
- exactly three public A datasets exist, with the approved schemas;
- the private parsed/validated dataset exists in the pipeline graph but is not a public UC table;
- the old job is absent;
- `gps_features` and `mode_segments` are inactive and not written;
- `gold.mode_segment_predictions` identity and metadata are unchanged.

### Phase E — activate ingestion

Phase C's full-refresh update is the first activation; no second start command is needed. It requires explicit approval because it consumes Event Hubs and destroys old A state.

Do not introduce a new continuous job before the manual full-refresh update succeeds and post-run validation passes. The safest progression is:

1. execute and verify one manually initiated full-refresh update;
2. observe the A-only graph and data quality;
3. in a later reviewed change, declare a new continuous orchestration job if continuous operation is desired;
4. plan and deploy that job only with separate approval.

### Phase F — post-activation checks

- Confirm the pipeline update completes successfully and remains healthy.
- Confirm Bronze receives complete original payload text and Event Hubs provenance.
- Confirm valid v0.1/v0.2 rows reach observations with `raw_speed` unchanged and `_m` naming enforced.
- Confirm invalid rows retain original bodies and deterministic/all rejection reasons in quarantine.
- Submit controlled duplicate synthetic producer events only through an approved non-production test path, or inspect naturally repeated IDs, to verify bounded `event_id` deduplication without treating duplicates as quarantine failures.
- Confirm watermark state is tied to `event_hub_enqueued_at`, not `event_time`.
- Confirm neither `gps_features` nor `mode_segments` receives new writes.
- Confirm `gold.mode_segment_predictions` table identity, schema, history/version, and modification timestamp did not change.
- Monitor quarantine ratios and pipeline event logs before enabling ongoing orchestration.

## 7. Rollback plan

### A. Bundle deploy fails before pipeline configuration changes

No runtime or table rollback is needed. Preserve the failure output, rerun `bundle summary` and `bundle plan`, correct authentication/upload/configuration issues, and retry only after a new approval. Confirm the old pipeline remains IDLE and the old job remains paused or present as expected.

### B. Bundle deploy succeeds but pipeline definition is invalid

Do not start an update. Prefer fix-forward on a branch and redeploy the corrected A-only definition to the same pipeline ID. If urgent configuration rollback is required, deploy the prior known-good bundle revision to the same binding. That rollback may recreate the removed orchestration job with a different job ID; verify it remains paused. No A-table data is lost unless Phase C has already run.

### C. Reset/recreation succeeds but Event Hubs authentication fails

The approved Path R loss has already occurred: old A rows and checkpoints cannot be recovered. Correct the secret/policy/configuration through its separately controlled process, then repeat a full-refresh update to establish an unambiguous clean checkpoint. Do not weaken authentication or print secret material. The full refresh will again start at `latest` and may skip events retained before its initialization point.

### D. Bronze ingests but observations/quarantine logic fails

Do not enable continuous orchestration. Preserve diagnostic pipeline events and new Bronze data while assessing the failure. Fix production code minimally and choose normal update versus selective downstream full refresh based on whether the changed expressions are checkpoint/schema-compatible. Do not full-refresh Bronze by default at this stage: doing so would lose newly ingested rows and, with `startingOffsets=latest`, would not replay them. If a selective refresh is necessary, first resolve the exact private/public dataset names from the deployed graph and obtain explicit approval.

### E. Most new events go to quarantine because the mobile producer is stale

Treat this as a producer-contract failure, not a reason to silently accept `vertical_accuracy` or relax validation. Do not enable ongoing orchestration. Coordinate a producer correction against the authoritative schema, retain quarantine evidence, and resume only after compatible events are demonstrated. Already accepted Path R loss remains accepted; new quarantined rows should be retained for diagnosis unless a separately approved cleanup occurs.

### F. Deployment unexpectedly attempts to modify/drop `gold.mode_segment_predictions`

Abort before approval or execution. Do not deploy. Investigate bundle state, resource bindings, and the generated plan until all Gold actions disappear. Record the Gold table identity/version before migration. Because execution is prohibited in this condition, no rollback should be necessary.

Rollback limits under Path R: bundle configuration can be redeployed or fixed forward, but old Pipeline A data and checkpoints destroyed by full refresh are intentionally not recoverable. Loss or mutation of Gold or unrelated resources is not accepted.

## 8. Commands requiring explicit approval

There are five explicit-approval actions in the recommended lifecycle.

```text
REQUIRES EXPLICIT APPROVAL
databricks bundle deploy --profile CANOPY_DEV -t dev --fail-on-active-runs
Purpose: Update the bound pipeline specification/files and remove the obsolete bundle-managed job.
Expected effect: Same pipeline ID; CURRENT/A-only source and configuration; job 287743457610499 deleted; no pipeline update.
Rollback: Redeploy the prior known-good bundle revision to the same binding, or fix forward. A recreated legacy job might receive a new ID and must remain paused.
```

```text
REQUIRES EXPLICIT APPROVAL
databricks pipelines start-update 2a3ca390-4bad-4de4-81e5-98ed584008e1 --full-refresh --cause USER_ACTION --profile CANOPY_DEV --output json
Purpose: Cleanly rebuild all Pipeline A streaming data and state and perform the first activation.
Expected effect: Destructive loss of old A data/checkpoints, fresh A schemas, Event Hubs consumption beginning at latest offsets for the new checkpoint.
Rollback: Code/configuration can be fixed forward or redeployed; old A data/checkpoints cannot be recovered under Path R.
```

```text
REQUIRES EXPLICIT APPROVAL
DROP TABLE dbw_canopy_dev.silver.gps_features;
Purpose: Retire the inactive former Pipeline B feature streaming table after verifying it is inactive and unwritten.
Expected effect: Remove gps_features from Unity Catalog; no Pipeline A graph change.
Rollback: Use Unity Catalog UNDROP within the supported recovery window if eligible.
```

```text
REQUIRES EXPLICIT APPROVAL
DROP TABLE dbw_canopy_dev.silver.mode_segments;
Purpose: Retire the inactive former Pipeline B/C segment streaming table after verifying it is inactive and unwritten.
Expected effect: Remove mode_segments from Unity Catalog; no Pipeline A graph change.
Rollback: Use Unity Catalog UNDROP within the supported recovery window if eligible.
```

```text
REQUIRES EXPLICIT APPROVAL
Add a new continuous orchestration Job resource in a later reviewed change, then run databricks bundle deploy --profile CANOPY_DEV -t dev --fail-on-active-runs.
Purpose: Provide ongoing Pipeline A execution only after the manual first run is proven healthy.
Expected effect: Create a new bundle-managed job that invokes the preserved pipeline ID; no old A/B/C job is restored.
Rollback: Pause the new job and remove it from the bundle in a reviewed follow-up deployment.
```

## 9. Remaining risks

- Full refresh and `startingOffsets=latest` intentionally create a non-replayable gap for old development events and possibly for events arriving before the fresh query captures its initial latest offsets. This is accepted by Path R.
- Full refresh is not reset-only: it starts the pipeline and accesses Event Hubs. Reset and activation cannot be treated as separate approval boundaries with the recommended command.
- Bundle identity is safe only while deployment metadata remains bound to the stated pipeline. The immediate pre-deploy plan is mandatory.
- Removed B/C datasets persist as queryable inactive objects until separately dropped; users might mistake stale data for current output.
- The shared Kafka consumer group creates interference risk if any unobserved consumer starts concurrently. Recheck jobs, pipeline updates, and ownership immediately before activation.
- A configuration-only inspection cannot prove secret validity, Event Hubs authorization, or runtime graph success. Those are first exercised by the approved pipeline update.
- After Path R reset, reverting to the old combined implementation is not a data-restoring rollback and could conflict with the new schemas/state.
- The absence of Gold actions in the current plan must be reconfirmed immediately before deployment. Any Gold action is a hard blocker.


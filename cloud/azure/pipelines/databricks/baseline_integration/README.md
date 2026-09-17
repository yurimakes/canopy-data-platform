# Canopy Baseline integration status

This folder is the integration layer around the teammate-owned weekly summary / Personal / Global calculation files now merged into `main`.

## Canonical files now in main

- `cloud/azure/pipelines/databricks/baseline_policy.yaml`
- `cloud/azure/pipelines/databricks/sync_confirmed_trips.py`
- `cloud/azure/pipelines/databricks/build_weekly_summary.py`
- `cloud/azure/pipelines/databricks/build_personal_baseline.py`
- `cloud/azure/pipelines/databricks/build_global_baseline.py`
- `shared/schemas/databricks_job_weekly_summary.json`

Canonical Gold paths currently merged by the teammate are:

- `abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/`
- `abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/personal_baseline_history/`
- `abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/global_baseline_history/`

Environment variables remain supported so a future storage-layout change does not require calculation-code changes.

## Eligibility ownership

There is currently **no separate baseline-eligibility implementation in main**. The current Personal code only has the implicit technical condition `prior completed week exists and cumulative distance > 0`.

A teammate is expected to implement the actual Eligibility policy/module. This integration layer intentionally does not invent Trip-count, distance, duration, or participant thresholds.

Expected integration direction after that module lands:

```text
weekly Gold
→ teammate Eligibility result
→ Personal baseline calculation
→ Global baseline calculation
```

`CANOPY_BASELINE_ELIGIBILITY_PATH` is reserved as the runtime seam. The exact schema must be wired only after the teammate's canonical eligibility contract is merged.

## Why we are not creating/deploying the final Databricks Job now

A Databricks Job is the orchestration wrapper that chains several already-implemented tasks. It is larger than this WBS. The current JSON is treated as a draft orchestration definition, not a deployed final workflow.

For this step we validate the individual calculation code itself:

1. code imports/compiles;
2. Personal cumulative baseline executes on sample data;
3. Global equal-user average executes on sample data;
4. weekly Gold consumes canonical Trip carbon instead of re-defining emission factors;
5. runtime/Cosmos integration contract is checked.

After Eligibility and the remaining weekly tasks are merged, the team can assemble and deploy one final Job in the correct order.

## User feedback boundary

User issue feedback is not an automatic calculation override. Baseline input uses system-finalized Trip results (`status=ready`). Approved support cases can be handled later through a manual reward adjustment/audit flow.

## Cosmos latest Baseline

`publish_baseline_snapshots.py` is prepared to publish ADLS Gold Personal/Global snapshots to Cosmos latest-read documents using Managed Identity/RBAC. The actual Baseline container names and partition keys must come from the canonical Cosmos design before Azure runtime smoke testing.

## Completion gate

Code-level execution tests can pass before the final Job exists. WBS final completion still requires the real Azure runtime checks that belong to the integration phase: ADLS read/write, Cosmos publish/read-back, and downstream API/reward consumption.

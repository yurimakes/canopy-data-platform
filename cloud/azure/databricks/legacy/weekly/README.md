# Weekly — 5dt024

This independent Bundle owns an actual ETL Pipeline and a scheduled Job:

1. Snapshot managed final Trips and existing Cosmos users, membership, missions,
   paid Trip ledger and previous ranking into owned managed staging tables.
2. Run `canopy-weekly-etl-trial` as a finite `pipeline_task`: weekly aggregates,
   commute eligibility, Personal/Global, changes, missions, paid-ledger rankings,
   campaign KPI and application projections.
3. Validate outputs and atomically publish the snapshot pointer to Cosmos.

No additional reward is paid here. Ranking sums already-paid Trip ledger entries.
Policy files and eligibility rules remain those of the imported runtime.
Mission/effective-baseline transforms execute in pandas workers without external
Cosmos access. Retries reuse the same snapshot; a failed ETL cannot publish.

Names have prefix `[dev 5dt024]`; catalog `dbw_canopy_trial`, schema `gold_5dt024`.
Schedule: Monday 00:10 Asia/Seoul, PAUSED by default. The final Trip Bundle must
have produced its managed final_trips table first. No upstream resource is altered.
Authenticate as `user@example.invalid`, then run `databricks bundle validate -t trial`
and `databricks bundle deploy -t trial` from this folder. The new owned secret
scope `canopy-downstream-5dt024` needs `cosmos-key`; never commit the value.

For manual checks set Job parameter `publish_mode=validate`: staging and ETL tables
are updated, but Cosmos is not changed. Enable scheduling only after cloud checks.

## Enable / pause with Bundle deployment

Run from `pipelines/weekly`:

```bash
databricks bundle deploy -t trial --var="weekly_schedule_pause_status=UNPAUSED"
databricks bundle deploy -t trial --var="weekly_schedule_pause_status=PAUSED"
```

Verify task and ETL update state in Jobs & Pipelines after deployment. Pausing the
trigger prevents future automatic runs; inspect and cancel an active run separately
when stopping an experiment. Never use an upstream Bundle for these new resources.

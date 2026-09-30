# Final Trip — 5dt024

Independent downstream Bundle. Name: `[dev 5dt024] canopy-final-trip-trial`.
Does not bind to or edit any 5dt016 Job/Pipeline.

Inputs are the canonical Silver `mode_segments`, `trip_ended_events` and
`gps_observations` tables plus Cosmos `trips` lifecycle. The adapter checks owner,
generation, complete sequence coverage, overlap, timestamps and duplicate
conflicts. It retains upstream modes/distances; it never runs inference again.
Commute verification uses captured home/work coordinates and observed endpoints.

Output is managed `dbw_canopy_trial.gold_5dt024.final_trips`, followed by a
conditional Cosmos ready projection. Same-generation replay cannot replace a
different result. A crash after Gold commit resumes Cosmos publication from Gold.
Trip reward settlement remains in the existing application/API domain, as in
the validated temporary Azure implementation; this job does not pay again.

This Bundle owns both an actual Lakeflow ETL Pipeline (`canopy-final-trip-etl-trial`)
and a Continuous Job. The pipeline reads managed Silver and computes managed Gold;
Cosmos writes never occur inside declarative functions. A single bounded Job task
freezes lifecycle/prior-Gold inputs, starts and awaits a finite pipeline update,
then publishes verified results with Cosmos compare-and-swap.

Continuous Jobs do not support task dependencies. A continuous pipeline task
would also prevent a later publication task from completing. Therefore this
wrapper sequences the finite update via the Pipeline API. Weekly instead uses
three dependent tasks in a scheduled Job. This is microbatch processing; latency
must be measured before enabling an always-on production workload.

Set Job parameter `publish_mode=validate` for a bounded manual check without
Cosmos publication. Its staging and managed Gold tables are still updated.

```powershell
databricks bundle validate -t trial
databricks bundle deploy -t trial
```

Use authenticated `user@example.invalid` against the target host. Deploy
defaults to PAUSED. Inputs must already exist and be readable. The new secret
scope `canopy-downstream-5dt024` must contain `cosmos-key`; never put its value
in Bundle variables, Git or command logs. Enable only after access and Cosmos
contracts are verified. No upstream service is started by this deployment.

Local test command from repository root (Python with existing runtime deps):
`python -m pytest tests/downstream -q`.

## Enable / pause with Bundle deployment

Run from `pipelines/final-trip`:

```bash
databricks bundle deploy -t trial --var="final_trip_continuous_pause_status=UNPAUSED"
databricks bundle deploy -t trial --var="final_trip_continuous_pause_status=PAUSED"
```

Verify task and ETL update state in Jobs & Pipelines after deployment. Pausing the
trigger prevents future automatic runs; inspect and cancel an active run separately
when stopping an experiment. Never use an upstream Bundle for these new resources.

# Personal stack app cutover — 2026-09-21

Main API `func-canopy-dev` now publishes to `evh-personal-5dt024`. The resident original personal ML/Trip Job `421770332247848` reads that GPS table and publishes into existing `canopy-db`; the app URL, accounts and reward records remain in place. No EAS rebuild is needed for this server-side routing change.

The previous eight Canopy Jobs have no active runs and their continuous/scheduled triggers are paused. All five previous pipelines are IDLE. Their source code and tables were preserved. ADF `adf-canopy-dev` has no registered triggers to restart the old path.

Active stack:

- GPS: `c54de8c4-1240-4835-97b3-e5db2a835e67`, RUNNING.
- Original resident ML + Trip: `421770332247848`, UNPAUSED, fresh ready heartbeat.
- Original Weekly: `402768089239280`, Monday 00:10 Asia/Seoul, UNPAUSED. Manual run `679493455871420` succeeded and published Cosmos projections.

History migration `294146716532335` verified all eight existing Gold documents by hash and readback. They were copied to `dbw_canopy_trial.personal_app_gold_5dt024.final_trips`. It did not republish rewards. Weekly outputs use `personal_app_weekly_5dt024`. The old isolated replay database is not the app database.

## HTTP acceptance

Two 31-point synthetic walking trips used the same main HTTP endpoints as the installed app, with real signup, KTDB quote/prepare, GPS, Stop, result, repeated comparison, history and community requests. Stop-to-result was **27.203 s / 27.265 s**. Original model version: `local-speedtransformer-playground-v1-transit-v3-quality-v1`. Both completed; short-trip comparisons returned `no_reduction` with zero points. This is not a positive reward amount test or a physical iPhone background-location test.

The first cutover test revealed a separate API issue: `ConnectionLostError` during immediate Trip-end publication left the durable outbox pending until the minute-based retry. Those pre-fix HTTP results were 90.5 s / 44.985 s; the first worker itself took 14.902 s. Added two bounded SDK retries with the same event ID before durable recovery. Existing send/auth/socket limits remain. See [Microsoft's Event Hubs retry options](https://learn.microsoft.com/en-us/python/api/azure-eventhub/azure.eventhub.eventhubproducerclient?view=azure-python).

Only `services/trip_lifecycle.py` and the health release marker were patched in the existing deployed package, verified byte-for-byte against all other package entries. Health release: `8aae8ff058a0d39908ea48108c8c608a1ff2b5a7791807eb484373ddb6b9be4a`. Local lifecycle/dispatch tests: 13 passed. Original Databricks runtime/model/reference files: all 261 hashes unchanged.

Pipeline configuration and public evidence are in canopy-databricks-pipelines, `pipelines/personal-stack/evidence/app-cutover-2026-09-21.json`. API cutover helper: `tools/azure/switch_personal_stack.py`; it guards old-writer shutdown, successful history migration, current worker readiness, event-hub RBAC and settings readback. API redeployment preserves the selected Job rather than restoring the previous finalizer.

Keep the resident worker running for phone testing. Recheck its fresh ready heartbeat after any restart. Physical-phone result rendering, network interruptions and background collection still need on-device verification; these two HTTP timings are not a universal latency guarantee. Existing Power BI connections to the previous Gold schema are not redirected by this app cutover.

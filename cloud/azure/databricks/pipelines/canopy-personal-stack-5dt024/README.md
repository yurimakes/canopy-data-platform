# Personal Azure stack — 5dt024

The original personal e2e-20260920 stack contains three resources:

- `resources/ingestion.pipeline.yml`: continuous GPS ingestion.
- `resources/trip.job.yml`: resident ML + final Trip worker, with a reused model and Spark session, and provisional live predictions.
- `resources/weekly.job.yml`: original Monday 00:10 Asia/Seoul Weekly Job.

`runtime/` retains all 261 original modules, ML weights and reference files. Run `python tools/verify_source.py` to verify their hashes. Three entrypoints were also compared with the original live workspace. Bundle production mode preserves continuous pipeline behavior; it does not change workspace pricing.

## Phone service fixes (2026-09-21)

The current entrypoint is `service/resident_worker.py`. The original archived entrypoint remains unchanged for comparison and rollback. No teammate ingestion/inference source is edited.

- `service/gps_reader.py` retains Silver `raw_speed` (m/s), previously dropped before inference.
- `service/phone_model.py` reuses the original weights, scaler and transit resolver. It converts valid device speed to km/h; uses the model's padding mask for short windows instead of repeating the last observed speed up to 200 times. Where device speeds exist, missing-speed gaps remain excluded quality intervals. A wholly sensorless input retains coordinate-speed fallback, explicitly identified in the model version. Distance calculation and reward policy are unchanged.
- `service/live_predictions.py` reads ongoing Trip GPS in the existing worker process and writes only a provisional `live_prediction` field to Cosmos. Updates use ETag compare-and-swap, skip ended Trips and older sequence numbers, and never award rewards. Final Trip processing runs independently. The API exposes the field only through the authenticated owner-scoped Trip route. The app expires predictions older than 30 seconds.
- GPS pipeline trigger interval is explicitly one second. This reduces scheduling waits; it does not promise one-second end-to-end results. Gold persistence/readback and Cosmos publication still precede final readiness.
- `service/gps_pipeline.py` uses `service/main_hub_ingestion.py` and the archived validation functions and adds `personal_silver_5dt024.gps_observations_live` in the same pipeline. A separate Kafka consumer `personal-5dt024-fast` runs the exact same contract parser, validity rules and event-id deduplication directly, avoiding the intermediate Bronze/parsed commit waits on the app path. Existing Bronze, Silver and quarantine tables are retained. Final reads fall back to legacy Silver for older Trips that predate the new consumer's retention window; conflicting sequences fail closed. No full refresh or checkpoint deletion is required.
- Small-volume phone testing uses four shuffle/state partitions. The actual pipeline runtime is DBR 18.3; `spark.sql.streaming.stateStore.partitions` supports [checkpoint-preserving state repartitioning](https://learn.microsoft.com/azure/databricks/structured-streaming/state-repartitioning) on this runtime. Size this setting again for production load rather than treating the test value as unlimited capacity. Changing only trigger frequency or adding the direct branch did not establish a latency improvement; compare the measured acceptance report.

`tests/` verifies sensor units, missing values, padding masks, full windows and Stop/live-write races. The actual reported all-walking Trip is replayed read-only; production history is not relabelled by hand. A single successful replay is not an accuracy benchmark across all transport modes.

## App destinations

|Destination|Value|
|---|---|
|Event Hub|evhns-canopy-dev / evh-canopy-gps-dev|
|Cosmos|cosmos-canopy-dev / canopy-db (existing app records)|
|GPS tables|dbw_canopy_trial.personal_bronze_5dt024 / personal_silver_5dt024|
|Final Trip|dbw_canopy_trial.personal_app_gold_5dt024.final_trips|
|Weekly|dbw_canopy_trial.personal_app_weekly_5dt024|
|Timing reports only|stcanopydev5dt / personal-5dt024|

Earlier comparison Cosmos database `canopy-personal-5dt024` and Gold schema `personal_gold_5dt024` are archived, not app destinations. App analytical data uses managed Delta tables; the app reads Cosmos.

Resource IDs: GPS `c54de8c4-1240-4835-97b3-e5db2a835e67`, Trip Job `421770332247848`, Weekly Job `402768089239280`.

## Cutover

1. Check no active app Trip. Pause previous Canopy Job triggers and stop their runs/pipelines. Preserve their source code and data.
2. Deploy with Jobs paused. Run `tools/migrate_app_history.py --source dbw_canopy_trial.gold_5dt024.final_trips --target dbw_canopy_trial.personal_app_gold_5dt024.final_trips` as a one-off serverless Python task. It validates document hashes and target readback without republishing rewards or changing the source.
3. Enable the original resident worker and Weekly schedule:

```bash
databricks bundle validate -t trial
databricks bundle deploy -t trial --var="trip_pause_status=UNPAUSED,weekly_pause_status=UNPAUSED"
databricks bundle run personal_gps -t trial
```

4. Wait for fresh `performance/resident-status.json` with state `ready`. In canopy-data-platform run `python tools/azure/switch_personal_stack.py --history-run-id <successful-history-run-id> --apply`. It verifies previous writers are stopped and changes the existing API's Event Hub and resident Job routing. API URL, auth and Cosmos records remain in place.
5. Test GPS -> Stop -> original ML -> Gold -> Cosmos -> HTTP result, comparison idempotency and history. Current cutover evidence: `evidence/app-cutover-2026-09-21.json`.

A default deployment pauses Job triggers. Supply the variables above to keep service active. A deployment can interrupt ingestion; check and start it again afterward. Keep the resident worker warm during phone testing.

## Historical isolated replay

Evidence files `main-replay-2026-09-21.json` and `main-projection-2026-09-21.json` describe tests BEFORE app cutover. Two 31-point walking trips took 37.094 and 32.704 seconds from Stop to Cosmos. These used direct Event Hub and TripService calls, excluded HTTP/mobile latency, and were not proof of faster app behavior. Initial malformed fixtures were excluded.

Weekly run 247993271187057 succeeded: behavior_change=2, next_week_missions=2, campaign_kpi=1. Personal/Global and paid reward outputs were empty for that insufficient-history fixture. This does not replace positive multi-week reward validation or physical phone tests.

## Existing Event Hub reconnection (2026-09-21)

The Function producer and personal ingestion use the existing `evhns-canopy-dev / evh-canopy-gps-dev`. The temporary `evh-personal-5dt024` hub is retired. Read authentication uses the existing `canopy-trial / canopy-databricks-listen` secret and SAS policy. Cosmos/storage credentials keep their existing scope.

New append-flow names `gps_events_evh_canopy_gps_dev_v1` and `gps_observations_live_evh_canopy_gps_dev_v1` isolate Kafka checkpoints from the retired topic. Existing table data is retained; derived Delta consumers, ML models and reward calculations are unchanged. Reading starts at the earliest retained event in the existing hub. All 261 archived runtime/model/reference files pass their original hash verification.

Reference: https://docs.databricks.com/aws/en/ldp/flow-examples

Keep Jobs paused and explicitly check/stop the continuous pipeline after configuration deployment, since changing its configuration can restart it.

# Event Hub → final Gold latency benchmark

One-shot serverless observer for the 5dt016 sandbox path.

It can be run **after the trip is already complete**. The job reads persisted
timestamps from Silver and the final Gold complete-payload table directly with
Spark, so no SQL Warehouse is required.

It reports:

- GPS Event Hub → validated p50/p95/max
- trip-end Event Hub → parsed
- trip-end parsed → final Gold
- **trip-end Event Hub → final Gold**
- **last GPS Event Hub → final Gold**
- last GPS validated → final Gold
- sequence completeness, segment count, and prediction count

The benchmark target is:

```text
Event Hub
   ↓
Silver GPS + trip_end
   ↓
stateful mode-detection/finalization pipeline
   ↓
dbw_canopy_trial.sandbox.jun_016_gold_complete_payloads
```

Deploy:

```bash
cd bundles/benchmarks/mode-detection-latency

databricks bundle deploy \
  -t sandbox \
  --profile CANOPY_TRIAL
```

Run after publishing a replay:

```bash
databricks bundle run \
  -t sandbox \
  --params trip_id=<TRIP_ID>,timeout_seconds=600 \
  mode_detection_latency_observer \
  --profile CANOPY_TRIAL
```

The job prints one `EH_TO_GOLD_LATENCY_REPORT` JSON object.

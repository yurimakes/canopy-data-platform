# Event Hub → final Gold → Cosmos latency benchmark

One-shot serverless observer for the 5dt016 sandbox path. It can be run after
the trip is already complete.

The observer reads persisted Silver/Gold timestamps and then reads the matching
Cosmos document by `trip_id + user_id`. It requires the Cosmos
`finalization_hash` to match Gold before reporting success.

It reports both durable boundaries:

- GPS Event Hub → validated p50/p95/max
- trip-end Event Hub → parsed
- trip-end Event Hub → final Gold
- last GPS Event Hub → final Gold
- **Gold final → Cosmos**
- **trip-end Event Hub → Cosmos**
- **last GPS Event Hub → Cosmos**

Deploy:

```bash
cd bundles/benchmarks/mode-detection-latency
databricks bundle deploy -t sandbox --profile CANOPY_TRIAL
```

Run after a replay:

```bash
databricks bundle run \
  -t sandbox \
  --params trip_id=<TRIP_ID>,timeout_seconds=600 \
  mode_detection_latency_observer \
  --profile CANOPY_TRIAL
```

The job prints one `EH_TO_COSMOS_LATENCY_REPORT` object.

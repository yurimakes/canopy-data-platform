# Mode-detection latency benchmark

One-shot serverless observer for the dedicated 5dt016 sandbox path.

It polls the sandbox Silver GPS/trip-end tables and the sealed mode-detection
result directly with Spark. No SQL Warehouse is required.

Deploy:

```bash
cd bundles/benchmarks/mode-detection-latency
databricks bundle deploy -t sandbox --profile CANOPY_TRIAL
```

Run after publishing a replay:

```bash
databricks bundle run -t sandbox \
  --params trip_id=<TRIP_ID>,timeout_seconds=600 \
  mode_detection_latency_observer \
  --profile CANOPY_TRIAL
```

The job prints one `MODE_DETECTION_LATENCY_REPORT` JSON object containing
ingestion latency percentiles, trip-end parsing latency, mode-detection sealing
latency, sequence completeness, segment count, and prediction count.

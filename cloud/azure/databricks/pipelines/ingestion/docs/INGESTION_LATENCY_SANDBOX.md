# Ingestion latency sandbox

This target isolates latency experiments from the production-shaped ingestion path.

## Isolation

- Event Hub: `evh-canopy-sandbox`
- Consumer group: `canopy-ingestion-latency`
- Catalog: `dbw_canopy_trial`
- Schema: `sandbox`
- Tables:
  - `dbw_canopy_trial.sandbox.bronze_events`
  - `dbw_canopy_trial.sandbox.silver_gps_observations`
  - `dbw_canopy_trial.sandbox.silver_gps_quarantine`
  - `dbw_canopy_trial.sandbox.silver_trip_ended_events`

The normal `trial` target remains unchanged and continues to use the production-shaped Bronze/Silver tables.

## Baseline trigger

The sandbox target sets:

```
pipelines.trigger.interval = 1 second
```

Change only `ingestion_trigger_interval` between experiments.

Examples:

```bash
databricks bundle validate -t ingestion_latency
databricks bundle deploy -t ingestion_latency
```

Override the trigger without editing tracked configuration:

```bash
databricks bundle validate -t ingestion_latency --var="ingestion_trigger_interval=5 seconds"
databricks bundle deploy -t ingestion_latency --var="ingestion_trigger_interval=5 seconds"
```

For the omitted/default control, temporarily remove the target-level
`pipelines.trigger.interval` configuration rather than assigning a synthetic value.

## Safety

Do not publish latency-test replay events to `evh-canopy-gps-dev`.

Do not point the sandbox target at the production `bronze` or `silver` schemas.

The sandbox Event Hub should have the dedicated consumer group
`canopy-ingestion-latency` before starting the pipeline.

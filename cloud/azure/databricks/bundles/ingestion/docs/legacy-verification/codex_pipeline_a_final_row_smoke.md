PIPELINE A FINAL ROW SMOKE CHECK

## Execution

Inspected the three Pipeline A tables after successful normal update `3bda57db-2383-43a8-b99c-b6e49c773a90`.

A transient one-shot serverless notebook task was used:

```text
Submit run: 309338483154720
Task run:   598816596020705
Result:     SUCCESS
Spark:      4.2.0
Timezone:   Etc/UTC
```

The task performed read-only Unity Catalog queries. No stopped SQL warehouse was started. The temporary workspace notebook and local script were removed afterward. No code, pipeline, Job, table, or Event Hubs configuration was modified.

## Row counts

```text
Bronze rows:      0
Observation rows: 0
Quarantine rows:  0
```

## Bronze

No Bronze rows were available. Therefore, body presence/raw JSON preservation, Event Hubs provenance population, and ingestion timestamps could not be verified from actual records.

## Observations

No observation rows were available. The duplicate query returned zero duplicate `event_id` groups, but live deduplication and field integrity were not exercised by data.

The deployed observation columns still include `raw_speed`, `vertical_accuracy_m`, `quality_flags`, and all approved provenance/timestamp fields. Stale `vertical_accuracy` is absent.

## Quarantine

No quarantine rows or rejection reasons were available. Body retention, reason-array content, and row-level provenance could not be sampled.

Top quarantine reason: none.

## Final status

**B. NO INPUT TRAFFIC AVAILABLE**

Bronze remains empty after the successful normal update. No evidence of a data-flow defect was observed, but no real records exist to complete row-level validation. No synthetic traffic was generated.

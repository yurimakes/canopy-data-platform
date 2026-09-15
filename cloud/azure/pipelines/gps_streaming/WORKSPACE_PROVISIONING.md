# GPS streaming workspace provisioning

This document records the actions that remain outside the repository. None of
them were performed while implementing the runtime adapter.

## Verified target

- Azure resource group: `5dt-2nd-team1`
- Azure Databricks workspace: `dbw-canopy-dev`
- Bundle profile: `CANOPY_DEV`
- Runtime: DBR `17.3.x-scala2.13` (Spark 4.0)
- Access mode: Standard (`USER_ISOLATION`)
- Unity Catalog catalog: `dbw_canopy_dev`

The `default` schema is not a deployment target. The bundle and Python config
reject it for Bronze, Silver, or Gold.

## Required before deployment

1. Create dedicated `dbw_canopy_dev.bronze`, `dbw_canopy_dev.silver`, and
   `dbw_canopy_dev.gold` schemas, or supply three other distinct existing
   schema names through bundle variables.
2. Create a Unity Catalog Volume for checkpoints. The development template
   expects `dbw_canopy_dev.bronze.canopy_checkpoints`, exposed as
   `/Volumes/dbw_canopy_dev/bronze/canopy_checkpoints`.
3. Grant the eventual job principal:
   - `USE CATALOG` on `dbw_canopy_dev`;
   - `USE SCHEMA` and `CREATE TABLE` on all three schemas;
   - `READ VOLUME` and `WRITE VOLUME` on the checkpoint volume;
   - read access to the registered MLflow model and alias; and
   - `CAN_USE` on the selected Job Compute policy.
4. Create or identify a Databricks secret scope and key containing an Event
   Hubs **listen-only** connection string. Grant the job principal secret read
   access. Never put the connection string in bundle variables or source.
5. Create or identify a dedicated Event Hubs consumer group and set the actual
   Kafka bootstrap server and Event Hub entity name. The bundle placeholders
   `REPLACE` must not be deployed.
6. Register the SpeedTransformer model in Unity Catalog and assign the intended
   alias. Set `model_uri` to that exact three-part model URI and alias.
7. Decide whether table creation is owned by provisioning or first job start.
   The entry point uses `CREATE TABLE IF NOT EXISTS`, so the job principal must
   retain `CREATE TABLE` if tables are not provisioned ahead of time.

## Deployment and run actions requiring explicit authorization

From this directory, a future operator can validate the resolved template:

```bash
databricks bundle validate --profile CANOPY_DEV -t dev
```

This read-only validation succeeded during implementation. A sync dry-run also
confirmed that the upload root is limited to `cloud/azure/pipelines` and no
workspace files were written.

After replacing every environment-specific value, these commands modify or
execute workspace resources and were intentionally not run:

```bash
databricks bundle deploy --profile CANOPY_DEV -t dev
databricks bundle run --profile CANOPY_DEV -t dev gps_streaming
```

Deploy creates or updates the job definition. Run creates Jobs compute, creates
missing tables when permitted, opens the Event Hubs consumer, and starts five
streaming queries.

## Checkpoint and state compatibility

- Keep all five checkpoint subdirectories durable and unique: `bronze`,
  `observations`, `quarantine`, `features-and-segments`, and
  `segment-inference`.
- Do not reuse a checkpoint with another source, table set, catalog, or job.
- The per-trip JSON envelope and neutral runtime snapshot are both versioned.
  An incompatible state change requires a deliberate migration or a new
  checkpoint; silently discarding production state is not supported.
- Changing detector seed, segment limits, grouping key, state schema, or table
  identities on an existing checkpoint requires compatibility review.
- The current mock contract rejects restored per-trip state whose persisted
  target is outside 250–300. A checkpoint containing an older target below 250
  requires deliberate migration or a new checkpoint before deployment.
- DBR 17.3 uses RocksDB by default; the bundle sets RocksDB and Avro encoding
  explicitly so state schema evolution is deliberate.

## Operational validation still required

Before accepting production traffic, run `TwsTester` on DBR 17.3, then execute
a synthetic Event Hubs replay in an isolated consumer group. Confirm:

- restart from checkpoint produces no duplicate feature or segment rows;
- malformed and unsupported payloads reach quarantine;
- per-trip ordering assumptions hold across micro-batches;
- Delta history contains the expected five stream commits;
- the model alias resolves and closed segments are scored; and
- checkpoint and state-store growth are bounded for the expected trip volume.

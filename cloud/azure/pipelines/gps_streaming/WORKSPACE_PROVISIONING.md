# GPS streaming workspace provisioning

This document records the remaining actions outside the repository for the
serverless Lakeflow deployment. Repository edits do not authorize workspace or
Azure mutations.

## Verified target

- Azure resource group: `5dt-2nd-team1`
- Azure Databricks workspace: `dbw-canopy-dev`
- Bundle profile: `CANOPY_DEV`
- Unity Catalog catalog: `dbw_canopy_dev`
- Execution target: serverless Lakeflow ETL pipeline
- Orchestration: continuous Databricks Job with one pipeline task
- Current pipeline channel: `PREVIEW` (required by the current
  `foreach_batch_sink` design)

The `default` schema is not a Canopy deployment target.

## Required Unity Catalog objects

Create or authorize creation of these schemas under the existing catalog:

- `dbw_canopy_dev.bronze`
- `dbw_canopy_dev.silver`
- `dbw_canopy_dev.gold`
- `dbw_canopy_dev.ml`

The expected tables are:

- `dbw_canopy_dev.bronze.gps_events`
- `dbw_canopy_dev.silver.gps_observations`
- `dbw_canopy_dev.silver.gps_quarantine`
- `dbw_canopy_dev.silver.gps_features`
- `dbw_canopy_dev.silver.mode_segments`
- `dbw_canopy_dev.gold.mode_segment_predictions`

The expected registered model is:

- `dbw_canopy_dev.ml.canopy_speedtransformer`
- development alias: `champion`
- URI: `models:/dbw_canopy_dev.ml.canopy_speedtransformer@champion`

A dedicated checkpoint Volume is **not** required for this Lakeflow target.
Lakeflow owns per-flow checkpoint/state lifecycle.

## Event Hubs prerequisites

Verified non-secret identifiers:

- namespace: `evhns-canopy-dev`
- Kafka bootstrap: `evhns-canopy-dev.servicebus.windows.net:9093`
- Event Hub: `evh-canopy-gps-dev`
- desired consumer group: `canopy-databricks`

Before deployment/run:

1. Create the dedicated consumer group if it does not exist.
2. Create a listen-only Event Hubs authorization rule; do not use
   `RootManageSharedAccessKey` for the stream.
3. Create a Databricks secret scope (development default: `canopy-dev`).
4. Store the listen-only connection string under the configured secret key
   (development default: `event-hubs-listen-connection-string`).
5. Grant the eventual runtime identity access to the secret.

Do not place the connection string in Git, bundle variables, shell history, or
logs.

## Model prerequisites

The repository snapshot lives under:

`ml/models/speedtransformer/artifacts/playground_v1`

The serverless pipeline dependency file is:

`cloud/azure/pipelines/gps_streaming/requirements.lakeflow.txt`

Before accepting integration success:

1. Register the artifact as `dbw_canopy_dev.ml.canopy_speedtransformer`.
2. Assign the intended `champion` alias.
3. Verify `mlflow.pyfunc.load_model()` resolves the alias URI from the
   serverless pipeline environment.
4. Run a known 200-speed smoke inference and verify the expected output columns:
   `predicted_class`, `confidence`, and `probabilities`.

## Permissions

Provisioning authority needs, at minimum:

- `USE CATALOG` and `CREATE SCHEMA` on `dbw_canopy_dev` (or equivalent owner /
  metastore-admin authority);
- authority to create/grant on the four schemas;
- authority to register the model in `dbw_canopy_dev.ml`;
- Azure permission to create the Event Hubs consumer group and listen-only SAS
  rule;
- Databricks permission to create/manage the secret scope and its ACL;
- permission to deploy the Declarative Automation Bundle.

The runtime identity needs, at minimum:

- `USE CATALOG` on `dbw_canopy_dev`;
- `USE SCHEMA` on bronze, silver, gold, and ml;
- the required table read/write privileges on the six pipeline tables;
- `CREATE TABLE` only if first-run table creation remains runtime-owned;
- `EXECUTE` / model access on
  `dbw_canopy_dev.ml.canopy_speedtransformer`;
- read access to the Databricks secret scope/key;
- Event Hubs listen access through the supplied SAS credential.

Classic Job Compute policy privileges, node type, worker count, DBR selection,
and manual checkpoint-Volume privileges are not part of the serverless
Lakeflow deployment contract.

## Bundle behavior

`resources/gps_streaming.pipeline.yml` defines the serverless pipeline.
`resources/gps_streaming.job.yml` defines a continuous Job whose pipeline task
references that pipeline resource.

The Job is intentionally configured with:

```yaml
continuous:
  pause_status: PAUSED
```

A bundle deployment may create/update resource definitions but must not begin
Event Hubs consumption while the Job remains paused.

Read-only validation to run before deployment:

```bash
cd cloud/azure/pipelines/gps_streaming

databricks bundle validate --profile CANOPY_DEV -t dev
databricks bundle sync --dry-run --profile CANOPY_DEV -t dev
```

Do not run `bundle deploy`, unpause the continuous Job, or invoke a pipeline
update until explicitly authorized.

## State compatibility

The stateful core persists a versioned JSON `ValueState` per `trip_id`.
The current detector contract is `mock-random-v2` with targets 250-300.

For the first Lakeflow integration deployment, use a fresh pipeline/flow state.
Do not attempt to migrate an old classic Structured Streaming checkpoint that
may contain `mock-random-v1` targets below 250.

Changing any of the following requires state/checkpoint compatibility review:

- detector version or seed semantics;
- segment target range;
- grouping key;
- `transformWithState` state schema;
- flow identity/name;
- table identities that participate in replay/idempotency.

Lakeflow manages checkpoints per flow. A full refresh or flow reset can cause
reprocessing; downstream ForEachBatch sinks therefore remain responsible for
idempotent writes. The existing feature/segment/prediction paths use Delta
`MERGE` keys for that reason.

## Integration validation still required

Before accepting the pipeline for production-like use:

1. Run the Spark `TwsTester` integration test in a compatible Databricks/Spark
   environment.
2. Validate the bundle resolves without classic-compute settings.
3. Deploy the pipeline/job resources while leaving the Job paused.
4. Confirm all four schemas, tables, secret references, and the model alias
   resolve under the intended runtime identity.
5. Run a bounded synthetic Event Hubs replay in an isolated consumer group.
6. Verify malformed/unsupported payloads reach quarantine.
7. Verify restart/reprocessing does not duplicate feature, segment, or scored
   prediction rows.
8. Verify a normal 250-point mock segment produces three 200-point model
   windows and a Gold prediction.
9. Inspect Lakeflow event logs/state metrics for unexpected state growth or
   serialization errors.
10. Only after the bounded run succeeds, decide whether to unpause the
    continuous Job for longer-running testing.

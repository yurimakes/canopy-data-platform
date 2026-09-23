# Canopy Databricks Bundles

Shared repository for the Canopy Databricks data/ML workloads.

## Repository layout

```text
canopy-databricks-pipelines/
├── bundles/
│   ├── ingestion/
│   │   ├── databricks.yml
│   │   ├── resources/
│   │   └── src/
│   ├── production-trip/
│   │   ├── databricks.yml
│   │   ├── resources/
│   │   └── src/
│   └── benchmarks/
│       ├── ingestion-latency/
│       │   ├── databricks.yml
│       │   ├── resources/
│       │   └── src/
│       └── end-to-segment/
│           ├── databricks.yml
│           ├── resources/
│           └── src/
├── shared/
│   ├── variables.yml
│   └── src/
├── legacy/
├── docs/
├── README.md
└── .gitignore
```

### Canonical deployable bundles

- `bundles/ingestion`
  - canonical Event Hubs ingestion pipeline
  - continuous wrapper job
  - Bronze/Silver ingestion outputs
- `bundles/production-trip`
  - canonical resident production-trip job
  - mode inference, segmentation, final-trip generation, and Cosmos DB publication

### HGB sandbox bundle

- `bundles/hgb-sandbox-5dt024` (target: `sandbox`)
  - isolated 5dt024 Event Hub ingestion pipeline and wrapper job
  - manual HistGradientBoosting analysis using 16 canonical features
  - verified synthetic ingestion, inference and Delta upsert; see bundle README
  - no operational Cosmos publication or app reward processing

### Benchmark bundles

- `bundles/benchmarks/ingestion-latency`
- `bundles/benchmarks/end-to-segment`

These are deployable Databricks bundles used for performance/latency measurement rather than production serving.

### Shared code

`shared/` contains configuration and code intended for reuse across bundle projects. The canonical bundles include `../../shared/*.yml`; `shared/variables.yml` currently owns the shared `catalog` variable. `shared/src/` is reserved for future reusable source code.

### Legacy

`legacy/` preserves workloads whose canonical deployment status has not yet been confirmed.
Nothing under `legacy/` is included by the canonical bundle configurations.

## Trial environment

- Databricks workspace host: `https://adb-7405612422597045.5.azuredatabricks.net`
- Unity Catalog catalog: `dbw_canopy_trial`
- CLI profile: `CANOPY_TRIAL`

The canonical `trial` targets use a shared deployment root:

```text
/Workspace/bundles/.bundle/canopy/<bundle-name>/trial
```

This is intentional: authorized collaborators deploying the same bundle/target resolve to the same bundle state instead of creating per-user copies.

The shared trial resources use the workspace `users` group as the project developer group. For `production-trip`, bundle-level `CAN_MANAGE` remains appropriate because the bundle contains only a job. For `ingestion`, `CAN_MANAGE` is scoped to the continuous wrapper job rather than applied bundle-wide; this avoids cross-user deployments trying to reconcile the Lakeflow pipeline owner through the pipeline permissions API. The pipeline keeps its existing workspace ACL/owner configuration. The bundle state is intentionally stored under `/Workspace/bundles` rather than the built-in `/Workspace/Shared` area.

## Existing canonical workspace resources

The canonical resources are already managed by the shared `trial` deployments. If bundle name, target, workspace, or resource mappings are changed later, verify the managed resource IDs with `bundle summary` / `bundle plan` before deploying. A `root_path` move by itself does not require rebinding when the CLI continues to report the same resources as already managed.

### Ingestion

```text
pipeline resource key: generic_event_ingestion_pipeline
pipeline ID:           2089be7f-2647-4a31-879c-14784dc56078

job resource key:      generic_event_ingestion_continuous
job ID:                313929125401537
```

From `bundles/ingestion`:

```bash
databricks bundle validate -t trial

databricks bundle deployment bind \
  generic_event_ingestion_pipeline \
  2089be7f-2647-4a31-879c-14784dc56078 \
  -t trial

databricks bundle deployment bind \
  generic_event_ingestion_continuous \
  313929125401537 \
  -t trial
```

### Production trip

```text
job resource key: production_trip
job ID:           32875321236425
```

From `bundles/production-trip`:

```bash
databricks bundle validate -t trial

databricks bundle deployment bind \
  production_trip \
  32875321236425 \
  -t trial
```

After binding, inspect the intended changes before deploying:

```bash
databricks bundle plan -t trial
databricks bundle deploy -t trial
```

The canonical jobs remain `PAUSED` by default in source control. A one-off ingestion deployment can override that without changing the repository:

```bash
databricks bundle deploy -t trial \
  --var="ingestion_continuous_pause_status=UNPAUSED"
```

## Collaboration workflow

An authorized collaborator can clone the repository, authenticate to the same workspace, enter a canonical bundle directory, and run:

```bash
databricks bundle validate -t trial
databricks bundle plan -t trial
databricks bundle deploy -t trial
```

Because `trial` uses a stable shared deployment root and bound resource IDs, the deployment manages the same workspace resources rather than creating a user-specific copy.

Do not run two `bundle deploy` operations against the same bundle/target at exactly the same time. Developers can work on Git branches concurrently, but shared-environment deployments should be serialized (or eventually handled by CI/CD).

## Benchmarks

Benchmark bundles are independent deployable bundles under `bundles/benchmarks/`. They should not be treated as passive result folders.

Validate them from their own directories:

```bash
cd bundles/benchmarks/ingestion-latency
databricks bundle validate -t trial

cd ../end-to-segment
databricks bundle validate -t trial
```

## Migration status

Shared deployment migration has been completed from the `5dt016` account.

Verified canonical state:

```text
ingestion pipeline: 2089be7f-2647-4a31-879c-14784dc56078
ingestion job:      313929125401537
production-trip:    32875321236425
```

Both canonical bundles deploy under:

```text
/Workspace/bundles/.bundle/canopy/<bundle-name>/trial
```

Post-deploy plans converged to no-op:

- ingestion: `0 add, 0 change, 0 delete, 4 unchanged`
- production-trip: `0 add, 0 change, 0 delete, 2 unchanged`

The remaining validation is cross-user: another teammate should run `bundle summary` and `bundle plan` with their own Databricks credentials and confirm the same paths/resource IDs with no resource creation.

Historical workloads remain under `legacy/` until their deployment/use status is reviewed.

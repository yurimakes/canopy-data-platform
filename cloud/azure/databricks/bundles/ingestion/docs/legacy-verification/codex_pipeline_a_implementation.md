IMPLEMENTATION RESULT

## 1. Summary

Implemented a self-contained Databricks Lakeflow Pipeline A for GPS ingestion on
branch `feature/pipeline-a-cleanup`.

The final dataflow is:

```text
Azure Event Hubs
        |
        v
dbw_canopy_dev.bronze.gps_events
        |
        v
private gps_events_parsed
       / \
      /   \
     v     v
dbw_canopy_dev.silver.gps_observations
dbw_canopy_dev.silver.gps_quarantine
```

Pipeline B/C, stateful trip processing, features, segments, Gold tables, MLflow,
PyTorch, SpeedTransformer, and inference configuration were removed. Production
code contains no explicit DDL, `writeStream`, `toTable`, manual checkpoint,
trigger, or `foreachBatch` orchestration.

The authoritative collector schema was vendored byte-for-byte from
`/home/aletheia/projects/canopy-data-platform/shared/schemas/gps.collector.schema.json`.
Its pinned SHA-256 is
`89131353ceb203c3dcf5f40a6fdd5c5df7a2a0ff85c7ce1e671a9799a8622261`.

No deployment, pipeline start, Event Hubs consumption, Azure mutation,
Databricks-table mutation, or existing-resource start/stop was performed.

## 2. Final repository tree

```text
.
├── .gitignore
├── README.md
├── codex_pipeline_a_implementation.md
├── databricks.yml
├── pyproject.toml
├── gps_ingestion/
│   ├── __init__.py
│   ├── deployment_config.py
│   ├── event_hubs_auth.py
│   ├── lakeflow_pipeline.py
│   └── spark_ingestion.py
├── resources/
│   └── gps_ingestion.pipeline.yml
├── schemas/
│   ├── gps.collector.schema.json
│   └── gps.collector.schema.metadata.json
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── gps_v0_1_valid.json
    │   ├── gps_v0_2_developer_valid.json
    │   └── gps_v0_2_user_valid.json
    ├── spark/
    │   ├── __init__.py
    │   ├── support.py
    │   ├── test_bronze_projection.py
    │   ├── test_observation_deduplication.py
    │   ├── test_observation_validation.py
    │   └── test_projections.py
    └── unit/
        ├── test_collector_schema.py
        ├── test_deduplication_contract.py
        ├── test_deployment_config.py
        └── test_event_hubs_auth.py
```

## 3. Files changed

- Rewrote `README.md` around the requested operational and contract sections.
- Removed Gold/ML/features/segments/predictions/model variables from
  `databricks.yml`; added configurable `deduplication_watermark` with a documented
  development default of `1 day`.
- Reduced `deployment_config.py` to the three Pipeline A tables and two schemas;
  renamed the class to `GpsIngestionTableConfig`.
- Retained and hardened `event_hubs_auth.py` with blank namespace/policy checks.
- Replaced `spark_ingestion.py` with schema, projection, validation, quarantine,
  and bounded-deduplication helpers only.
- Added `lakeflow_pipeline.py` with three public streaming tables and one private
  parsed/validated streaming table.
- Renamed only the resource file from `gps_streaming.pipeline.yml` to
  `gps_ingestion.pipeline.yml`; retained bundle name, pipeline resource key, and
  deployed pipeline name.
- Removed Preview-only and ML configuration; selected `channel: CURRENT`, UTC
  session timezone, and no `continuous: true` setting.
- Vendored the authoritative schema and adjacent provenance metadata.
- Added project/test metadata with no runtime dependencies.
- Replaced legacy B/C assertions with unit, Spark, fixture, projection,
  quarantine, and deduplication tests.

## 4. Final table contracts

### `dbw_canopy_dev.bronze.gps_events`

```text
body                    STRING NOT NULL
event_hub_topic         STRING
event_hub_partition     INT
event_hub_offset        BIGINT
event_hub_enqueued_at   TIMESTAMP
ingested_at             TIMESTAMP NOT NULL
```

`body` is the original Kafka value cast from UTF-8 bytes to string. It is not
parsed or reserialized before Bronze and Bronze is not deduplicated.

### `dbw_canopy_dev.silver.gps_observations`

```text
schema_version          STRING NOT NULL
event_id                STRING NOT NULL
user_id                 STRING NOT NULL
device_id               STRING NOT NULL
trip_id                 STRING NOT NULL
sequence                BIGINT NOT NULL
event_time              TIMESTAMP NOT NULL
received_at             TIMESTAMP NOT NULL
lat                     DOUBLE NOT NULL
lon                     DOUBLE NOT NULL
accuracy                DOUBLE
raw_speed               DOUBLE
altitude_m              DOUBLE
vertical_accuracy_m     DOUBLE
course_deg              DOUBLE
source                  STRING NOT NULL
quality_flags           ARRAY<STRING> NOT NULL
collection_mode         STRING
label                   STRING
event_hub_topic         STRING
event_hub_partition     INT
event_hub_offset        BIGINT
event_hub_enqueued_at   TIMESTAMP
bronze_ingested_at      TIMESTAMP NOT NULL
parsed_at               TIMESTAMP NOT NULL
```

Collector `speed` is copied to `raw_speed` without conversion or derivation.
`raw_location` and additional properties remain only in the Bronze body.

### `dbw_canopy_dev.silver.gps_quarantine`

```text
body                    STRING NOT NULL
schema_version          STRING
event_id                STRING
rejection_reason        STRING NOT NULL
rejection_reasons       ARRAY<STRING> NOT NULL
event_hub_topic         STRING
event_hub_partition     INT
event_hub_offset        BIGINT
event_hub_enqueued_at   TIMESTAMP
bronze_ingested_at      TIMESTAMP NOT NULL
quarantined_at          TIMESTAMP NOT NULL
```

## 5. Validation behavior

Spark VARIANT parsing distinguishes malformed JSON, a non-object top level,
missing paths, explicit JSON null, wrong JSON types, and invalid values.
Validation covers all authoritative rules:

- v0.1 and v0.2 schema versions;
- required-key presence, including required nullable keys;
- UUID-shaped identifiers;
- UTC `Z` timestamps before conversion to UTC Spark timestamps;
- sequence minimum `1`;
- coordinate and optional-number ranges;
- source enum;
- string-only unique quality flags;
- object-valued `raw_location`;
- v0.1 legacy label vocabulary without normalization;
- v0.2 user/null-label and developer/current-label compatibility;
- strict `vertical_accuracy_m` spelling;
- allowed unknown additional properties.

Reasons are ordered so the first element is the deterministic primary reason and
the complete ordered list is retained. Best-effort quarantine extraction only
retains `schema_version` and `event_id` when their JSON types are strings.

## 6. Deduplication behavior

Only observations are deduplicated:

```text
key              event_id
watermark column event_hub_enqueued_at
horizon          canopy.deduplication_watermark
dev default      1 day
```

This is bounded state, not permanent global uniqueness. Collector `event_time`
does not control ingestion lateness and can be arbitrarily old when mobile events
are buffered. Bronze retains duplicates and valid duplicates are not quarantine
errors.

## 7. Tests run

### Syntax compilation

Command:

```bash
python3 -m compileall -q gps_ingestion tests
```

Result: exit code `0`; no output.

### Unit tests

Command:

```bash
python3 -m unittest discover -s tests/unit -v
```

Exact result summary:

```text
Ran 12 tests in 0.001s

OK
```

All 12 unit tests passed.

### Spark tests

Command:

```bash
python3 -m unittest discover -s tests/spark -v
```

Exact result summary:

```text
Ran 0 tests in 0.000s

OK (skipped=4)
```

All four Spark test classes skipped with:

```text
optional PySpark test dependency is not installed
```

PySpark was not installed because it is optional for local tests and must not be
added to the Databricks Lakeflow runtime merely to make local imports pass.

### Pytest

Command:

```bash
python3 -m pytest -q
```

Result: exit code `1`:

```text
/usr/bin/python3: No module named pytest
```

### Schema pin and diff checks

The vendored schema compared byte-for-byte equal to the authoritative source.
`sha256sum` returned the pinned digest. `git diff --check` passed with no output.
The secret-pattern and forbidden Pipeline B/C configuration scans returned no
production findings.

## 8. Databricks bundle validation

Command:

```bash
databricks bundle validate --profile CANOPY_DEV -t dev
```

The first sandboxed attempt failed before validation because sandbox DNS/network
access was blocked while the CLI tried to refresh OAuth metadata. The same
read-only command was retried with approved network access and returned exit code
`0`:

```text
Name: canopy-gps-streaming
Target: dev
Workspace:
  Host: https://adb-7405605578654524.4.azuredatabricks.net
  User: user@example.invalid
  Path: /Workspace/Users/user@example.invalid/.bundle/canopy-gps-streaming/dev

Validation OK!
```

No deploy or pipeline run command was issued.

## 9. Git status and commit

Implementation commit:

```text
06ebab4 refactor: isolate GPS ingestion Pipeline A
```

The implementation commit contains 29 changed paths, 1,523 insertions, and 453
deletions. This report is added in a separate documentation commit so it can cite
the immutable implementation commit. The final documentation commit SHA is
reported in the terminal/final summary. Nothing is pushed.

## 10. Known limitations / risks

- Spark transformation and streaming-dedup tests were authored but not executed
  locally because PySpark/Java are absent. They should be run in a Spark 4 or
  Databricks environment with VARIANT support before deployment.
- The parser uses modern `try_parse_json`, `try_variant_get`, `schema_of_variant`,
  and `is_variant_null` functions. The selected current serverless Lakeflow
  runtime must expose these APIs.
- Existing Databricks table schemas and writers were intentionally not inspected
  or mutated. An incompatible pre-existing `vertical_accuracy` schema requires a
  separately approved migration/recreation plan.
- A fresh checkpoint uses `startingOffsets=latest`; retained Event Hubs history is
  not replayed automatically.
- Bounded deduplication can admit a retransmission after the configured horizon.
- `event_hub_enqueued_at` is nullable in the public contract even though Kafka
  normally supplies it. Null enqueue timestamps cannot provide normal watermark
  semantics and should be monitored.
- A null Kafka value violates the approved non-null Bronze body contract and fails
  the `body_is_not_null` Lakeflow expectation.
- The raw body and `raw_location` can contain sensitive device/provider context;
  Unity Catalog access and retention policy remain operational responsibilities.

## 11. Decisions or follow-up still required

1. Run the Spark suite in a supported Spark 4/Databricks test environment.
2. Inspect existing Pipeline A tables and any former combined pipeline before
   deployment; ensure exactly one active writer per public table.
3. Decide the deployed-table migration strategy if existing schemas differ.
4. Tune `deduplication_watermark` from observed retransmission timing and state
   size; `1 day` is only the development default.
5. Define a separate Databricks Job or other orchestration mechanism if continuous
   execution is desired. This resource intentionally omits `continuous: true`.
6. Establish an approved Bronze replay procedure before any full refresh or
   checkpoint reset.

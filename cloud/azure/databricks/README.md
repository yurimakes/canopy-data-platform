# Purpose

This repository defines Canopy Pipeline A: a self-contained Databricks Lakeflow
pipeline that ingests GPS event payloads from Azure Event Hubs into a durable raw
Bronze table, validates the collector contract once, and branches to validated
Silver observations or Silver quarantine.

# Input

The input is the Kafka-compatible endpoint for the development Event Hub:

```text
namespace       evhns-canopy-dev
Event Hub       evh-canopy-gps-dev
consumer group  canopy-databricks
SAS policy      canopy-databricks-listen
```

The authoritative JSON Schema is vendored at
`schemas/gps.collector.schema.json`. Provenance, source commits, and its SHA-256
are recorded in `schemas/gps.collector.schema.metadata.json`.

# Tables Created

Pipeline A is the sole intended writer of exactly these public tables:

```text
dbw_canopy_dev.bronze.gps_events
dbw_canopy_dev.silver.gps_observations
dbw_canopy_dev.silver.gps_quarantine
```

It also owns a private, pipeline-only `gps_events_parsed` table. The private table
parses and validates every Bronze row once before the two Silver branches.

# Processing Flow

```text
Azure Event Hubs
        |
        v
bronze.gps_events
        |
        v
private gps_events_parsed
       / \
      v   v
silver.gps_observations   silver.gps_quarantine
```

Lakeflow owns streaming state, checkpoints, and query lifecycle. Runtime
scheduling is intentionally not defined by this bundle resource.

# Schema

Bronze stores the complete UTF-8 Event Hubs value as `body`, together with topic,
partition, offset, enqueue timestamp, and ingestion timestamp. `body` is not
parsed, reserialized, normalized, deduplicated, or stripped of unknown fields.

Silver observations contain collector identity, timestamps, coordinates,
`accuracy`, device-provided `raw_speed`, altitude, `vertical_accuracy_m`, course,
source, quality flags, optional collection metadata, Event Hubs provenance, and
processing timestamps. Collector `speed` is renamed to `raw_speed` without unit
conversion or derivation. The collector obtains it from Expo Location's
instantaneous device speed in metres per second. Pipeline A computes no other
speed.

`raw_location` and arbitrary additional properties are intentionally excluded
from observations. They remain recoverable from the unchanged Bronze body.

# Validation / Quarantine

The parser uses Spark VARIANT inspection so it can distinguish malformed JSON,
the wrong top-level JSON type, a missing key, explicit JSON null, a wrong field
type, and an invalid value. Required nullable keys must exist, although their
values may be null where the schema permits it.

Both `canopy.gps.collector.v0.1` and `canopy.gps.collector.v0.2` are accepted.
v0.1 label values are preserved unchanged and `collection_mode` is never inferred.
v0.2 enforces the authoritative user/null-label and developer/current-label
combinations. Labels are never normalized. Only `vertical_accuracy_m` is accepted;
the stale `vertical_accuracy` spelling is not an alias.

Quarantine preserves the original body and Event Hubs coordinates, a deterministic
primary reason, and an ordered array of all violations. `schema_version` and
`event_id` are best-effort extractions. Duplicate valid events are not quarantine
errors.

# Deduplication

Only Silver observations are deduplicated, using `event_id` within a configurable
watermark on `event_hub_enqueued_at`. The development default is `1 day`; it is a
configuration default, not a permanent architectural guarantee.

```text
event_hub_enqueued_at -> ingestion arrival and bounded deduplication state
event_time             -> user trajectory and measurement chronology
```

An event repeated after the configured state horizon can appear again. Bronze is
never deduplicated.

# Configuration

`databricks.yml` defines the existing development catalog, Bronze/Silver schemas,
three table names, Event Hubs non-secret identifiers, secret scope/key, and the
deduplication watermark. The workspace remains `dbw-canopy-dev`. The pipeline
uses the current Lakeflow channel and UTC Spark session timezone.

# Event Hubs Authentication

The Databricks secret `canopy-dev/canopy-databricks-listen` contains only the SAS
policy key. The pipeline retrieves it at runtime and constructs the connection
string and Kafka JAAS configuration in memory. Neither value is logged or stored
in source control.

# Replay / Failure Behavior

Lakeflow checkpoints resume normal processing. `startingOffsets=latest` applies
when no checkpoint exists, so a fresh pipeline state consumes only events arriving
after startup. It does not replay old Event Hubs retention automatically. Replay
from Bronze should use the durable raw table and a separately reviewed procedure.

Full refreshes, flow renames, or checkpoint loss can change replay behavior. Before
activation, operators must verify that no former combined pipeline or other writer
is simultaneously writing any of the three public tables or using the consumer
group in a conflicting way.

# Testing

Pure unit tests need only Python's standard library. Spark tests require an
optional local Spark 4 runtime with VARIANT support, or a Databricks test
environment. PySpark is not a Lakeflow runtime dependency.

```bash
python3 -m unittest discover -s tests/unit -v
python3 -m unittest discover -s tests/spark -v
databricks bundle validate --profile CANOPY_DEV -t dev
```

Tests never require live Event Hubs access.

# What This Pipeline Does NOT Do

This repository does not calculate distance, derived or rolling speed, GPS
features, transitions, trip state, segments, or transport-mode predictions. It
does not use `transformWithState`, MLflow, SpeedTransformer, PyTorch, model URIs,
Gold tables, or inference handlers. Those responsibilities belong outside
Pipeline A.

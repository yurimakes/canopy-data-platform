# Canopy Generic Event Ingestion

## Purpose

This repository defines the Trial ingestion boundary for Canopy.

It consumes the shared Azure Event Hubs stream once, stores every event in a
generic Bronze table, and routes supported event contracts into typed Silver
tables.

The current migration target is **Trial only**:

```text
workspace: dbw-canopy-trial
profile:   CANOPY_TRIAL
catalog:   dbw_canopy_trial
schema:    sandbox
```

Legacy `dbw-canopy-dev` is reference-only and must not be modified by this
branch.

## Event Hubs input

```text
namespace       evhns-canopy-dev
Event Hub       evh-canopy-gps-dev
consumer group  canopy-databricks-trial
SAS policy      canopy-databricks-listen
secret scope    canopy-trial
secret key      canopy-databricks-listen
```

The Trial consumer group is intentionally separate from legacy consumers.

## Tables created

```text
dbw_canopy_trial.sandbox.bronze_events
dbw_canopy_trial.sandbox.silver_gps_observations
dbw_canopy_trial.sandbox.silver_gps_quarantine
dbw_canopy_trial.sandbox.silver_trip_ended_events
```

The pipeline also owns one private Lakeflow table:

```text
gps_events_parsed
```

## Processing flow

```text
Azure Event Hubs
        |
        v
sandbox.bronze_events
        |
        +--> GPS schema_version
        |       |
        |       v
        |   private gps_events_parsed
        |      / \
        |     v   v
        | silver_gps_observations
        | silver_gps_quarantine
        |
        +--> event_type=trip_ended
                |
                v
            silver_trip_ended_events
```

Unknown event types remain durably available in Bronze and are not forced into
an unrelated Silver contract.

## Generic Bronze contract

Bronze is intentionally blind to domain-specific payload fields. It preserves the
raw UTF-8 body and extracts only routing/provenance metadata:

```text
raw_payload
event_id
event_type
schema_version
event_hub_topic
event_hub_partition
event_hub_offset
event_hub_enqueued_at
ingested_at
```

Fields such as `trip_id`, GPS coordinates, lifecycle timestamps, and model
features belong in typed downstream tables, not Bronze.

## GPS Silver contract

Supported GPS contracts:

```text
canopy.gps.collector.v0.1
canopy.gps.collector.v0.2
```

Valid observations are written to:

```text
dbw_canopy_trial.sandbox.silver_gps_observations
```

Operational timestamps:

```text
event_hub_enqueued_at
bronze_ingested_at
parsed_at
validated_at
```

Rejected GPS payloads are written to:

```text
dbw_canopy_trial.sandbox.silver_gps_quarantine
```

with:

```text
bronze_ingested_at
quarantined_at
```

GPS Silver observations are deduplicated by `event_id` within the configured
watermark on `event_hub_enqueued_at`. Bronze is never deduplicated.

## trip_ended Silver contract

The primitive lifecycle contract is routed when:

```text
event_type    = trip_ended
schema_version = trip-lifecycle-v1
```

Valid events are written to:

```text
dbw_canopy_trial.sandbox.silver_trip_ended_events
```

Operational timestamps:

```text
event_hub_enqueued_at
bronze_ingested_at
parsed_at
```

## Timestamp semantics

The ingestion layer preserves source timestamps and adds semantically named
operational timestamps only:

```text
event_hub_enqueued_at  Azure Event Hubs enqueue time
ingested_at            generic Bronze processing time
parsed_at              typed payload parsing/validation time
validated_at           valid GPS Silver emission time
quarantined_at         rejected GPS Silver emission time
```

Latency benchmarking is intentionally deferred until the complete Canopy path is
connected.

## Lakeflow runtime

The bundle defines a serverless Lakeflow pipeline using the CURRENT channel.
The pipeline is not declared continuous by this bundle; manual/triggered updates
are valid for migration smoke testing.

Kafka source behavior:

```text
startingOffsets = latest
failOnDataLoss  = true
```

On a fresh checkpoint, only events arriving after startup are consumed. Existing
Lakeflow checkpoint state controls subsequent incremental reads.

## Configuration

`databricks.yml` targets:

```text
workspace host:
https://adb-7405612422597045.5.azuredatabricks.net

profile:
CANOPY_TRIAL

catalog/schema:
dbw_canopy_trial.sandbox
```

No deployment from this branch should target `CANOPY_DEV`.

## Validation

Local:

```bash
python3 -m unittest discover -s tests/unit -v
python3 -m unittest discover -s tests/spark -v
```

Trial bundle:

```bash
databricks bundle validate -t trial
databricks bundle deploy -t trial
```

## Out of scope

This pipeline does not perform transportation-mode inference, smoothing,
segmentation, trip finalization, Gold aggregation, CosmosDB publication, or
mobile/API serving.

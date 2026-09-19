# Standard vs real-time inference execution

## Standard continuous baseline

The replay inference pipeline remains a standard Lakeflow streaming table backed by
Delta input/output. Its trigger interval is configurable with
`continuous_replay_trigger_interval` and defaults to `1 second`.

A controlled `0 seconds` experiment is allowed only through a bundle override.
The current Databricks property reference documents the value format as a number
plus a supported time unit, but does not explicitly document zero as a recommended
or guaranteed setting. Treat acceptance and runtime behavior as an experiment, not
as a production contract.

## Real-time mode constraint

Lakeflow real-time mode is not a drop-in execution-mode switch for the current
Pipeline B architecture. Current Databricks real-time mode does not support Delta
as either source or sink. It supports Event Hubs through the Kafka-compatible
connector and requires a real-time update flow.

Therefore the meaningful architectural comparison is:

- Standard path: Delta silver observations -> stateful inference -> Delta predictions
- Real-time path: Event Hubs/Kafka -> stateful inference -> Event Hubs/Kafka or
  another supported sink, with later persistence to Delta if required

This changes the system boundary and must be benchmarked separately rather than
presented as an equivalent execution setting for the existing Delta-to-Delta
pipeline.

## Cost interpretation

Azure pricing currently lists Lakeflow Spark Declarative Pipelines serverless
compute as one DBU-priced workload and does not publish a separate real-time
Lakeflow DBU rate. Real-time mode can nevertheless consume more DBUs because it
keeps dedicated resources continuously available and requires enough task slots to
run all query stages concurrently. Compare actual DBU consumption in billing
system tables during A/B tests rather than assuming equal total cost.

# Real-time inference variant follow-up

Status: **Deferred**

## Context

The current mode-inference pipeline is a standard Lakeflow continuous pipeline:

```text
Delta silver/replay GPS observations
-> transformWithState
-> incremental feature extraction
-> LightGBM pointwise inference
-> Delta mode predictions
```

Latency work on the standard path has already removed the main application-side
bottlenecks:

- state-store partitions reduced to 4 for the replay workload;
- state migrated from JSON to bounded native state;
- point history migrated to sequence-keyed MapState to avoid full-window rewrites;
- feature extraction made incremental;
- stage telemetry added around processor entry, feature computation, and prediction.

The remaining latency is dominated by the time before the Python state processor
starts, not by feature computation itself.

## Current standard-mode baseline

The replay pipeline supports a configurable
`continuous_replay_trigger_interval`.

A controlled `0 seconds` experiment was accepted by the current Databricks
runtime and produced the following representative result for 5 users x 300 points:

- average visible -> processor: ~1.70 s;
- p50 visible -> processor: ~1.80 s;
- p95 visible -> processor: ~2.76 s;
- average processor -> feature start: ~22 ms;
- average feature computation: ~0.05 ms;
- average feature -> prediction: ~0.41 s;
- average visible -> prediction: ~2.13 s;
- final prediction readiness wait: 0 ms in that run.

The `0 seconds` setting is therefore useful as a development experiment, but it
should not be treated as a guaranteed production contract unless Databricks
documents that value explicitly for the deployed runtime/channel.

## Why real-time mode is not a drop-in switch

As of September 2026, Lakeflow real-time mode does not support Delta as a source
or sink. It does support Apache Kafka and Azure Event Hubs through the
Kafka-compatible connector.

Therefore the existing Delta-to-Delta Pipeline B cannot be converted to real-time
mode by changing only a pipeline setting.

The meaningful real-time variant changes the system boundary.

## Proposed real-time variant

Preferred Azure-native variant:

```text
                         +-> standard ingestion -> Delta silver_gps_observations
GPS Event Hub -----------+
                         +-> Lakeflow real-time inference
                                  |
                                  v
                         prediction Event Hub
                                  |
                                  v
                         standard persistence
                                  |
                                  v
                         Delta silver_mode_predictions
```

The existing GPS Event Hubs namespace can potentially be reused if its tier and
configuration support the Kafka-compatible endpoint. A separate consumer group
would isolate the real-time inference consumer from the ordinary ingestion
consumer.

A separate prediction Event Hub, topic, or equivalent supported streaming sink
would likely be needed for the real-time inference output because direct Delta
output is not supported by real-time mode.

Running a dedicated Kafka cluster is not required merely to use this path; Azure
Event Hubs can expose a Kafka-compatible interface.

## Stateful inference implications

The current inference implementation is conceptually reusable:

- `transformWithState` remains the stateful primitive;
- the bounded per-trip MapState remains appropriate;
- incremental feature extraction remains appropriate;
- the same model contract can be preserved.

However, real-time mode processes rows differently from standard microbatch mode.
The state processor must be validated under the real-time invocation model rather
than assumed to have identical batching behavior.

This should be treated as a separate replay prototype before any production
migration.

## Cost interpretation

Azure Databricks currently prices Lakeflow Spark Declarative Pipelines serverless
compute as a DBU-priced workload and does not publish a separate Lakeflow
real-time-mode DBU price on the Azure pricing page.

Equal DBU unit pricing does not imply equal total cost.

Real-time mode keeps query stages concurrently scheduled and requires enough task
slots for all stages at the same time. Its actual DBU consumption per wall-clock
hour can therefore differ materially from the standard continuous pipeline.

Any future comparison should measure:

- DBUs consumed per hour;
- effective cost per active trip / GPS event;
- source-to-prediction latency;
- idle-period cost;
- required task slots / concurrency;
- Event Hubs throughput and partition requirements.

## Decision for the current MVP

Do **not** implement the real-time variant now.

Keep the current standard Delta-based inference path as the MVP baseline and retain
real-time mode as an architectural option if standard-mode latency proves
insufficient for product requirements.

The current standard path is operationally simpler because:

- GPS observations already persist through the generic ingestion layer;
- inference input and output remain durable Delta tables;
- replay/debugging is straightforward;
- no additional low-latency output bus is required;
- downstream segmentation/finalization already consume the Delta contract.

## Revisit criteria

Reconsider the real-time variant if one or more of the following becomes true:

- measured production source -> prediction latency is too high for the mobile UX;
- trip finalization frequently waits on the final mode prediction;
- a sub-second prediction SLA becomes a product requirement;
- the service needs predictions pushed directly to an operational message bus;
- Databricks adds Delta source/sink support to Lakeflow real-time mode;
- standard-mode trigger and execution tuning no longer produces meaningful gains.

## Follow-up work when revisited

- [ ] Confirm the Event Hubs namespace tier supports the Kafka-compatible endpoint.
- [ ] Define a dedicated consumer group for real-time GPS inference.
- [ ] Decide whether to reuse the GPS Event Hub or create a dedicated input hub.
- [ ] Define the prediction Event Hub/topic and event schema.
- [ ] Prototype Event Hubs -> real-time transformWithState -> Event Hubs.
- [ ] Validate current MapState and model behavior under one-row real-time
      processing.
- [ ] Add a persistence consumer from predictions back into
      `silver_mode_predictions`.
- [ ] Compare Standard vs Real-time latency under the same event load.
- [ ] Compare measured DBU consumption and Event Hubs cost.
- [ ] Define rollback/fallback behavior before any production cutover.

## References

- Databricks real-time mode:
  https://docs.databricks.com/aws/en/ldp/real-time
- Azure Databricks pricing:
  https://azure.microsoft.com/pricing/details/databricks/

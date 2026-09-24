# Cosmos projection

Asynchronous consumer of durable final Gold trip payloads.

```text
Gold complete_payloads
        ↓
continuous projection worker
        ↓
Cosmos DB / canopy-db / trips
```

The worker is deliberately outside the stateful ML/finalization pipeline. A
Cosmos outage therefore does not stall mode detection or Gold publication.

Durability/idempotency is tracked in a managed Delta status table. A crash after
a Cosmos write but before the status MERGE is safe: the next attempt reads the
same Cosmos document and treats the matching `finalization_hash` as already
published.

Production-shaped behavior requires an existing lifecycle Trip document.
The sandbox target enables creation of missing documents only so standalone
Event Hub replay fixtures can exercise the complete path.

Repo defaults remain `PAUSED`.

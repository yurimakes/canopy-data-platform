# canopy-gps-ingestion

Private repository for Canopy Pipeline A: Azure Event Hubs GPS ingestion into Databricks Bronze, validated Silver observations, and Silver quarantine.

This repository was split from `aletheia-ops/canopy-data-platform` so ingestion can evolve independently from downstream feature engineering, transition detection, segmentation, and ML inference.

## Intended boundary

```text
Azure Event Hubs
      |
      v
Bronze: dbw_canopy_dev.bronze.gps_events
      |
      +--> Silver: dbw_canopy_dev.silver.gps_observations
      |
      +--> Silver: dbw_canopy_dev.silver.gps_quarantine
```

Downstream derived-speed computation, rolling features, `transformWithState`, transition detection, segmentation, MLflow/SpeedTransformer inference, and Gold prediction tables are intentionally outside this repository.

## Migration status

The initial commit preserves the reusable ingestion/auth/configuration code and focused tests from `canopy-data-platform`. Some migrated modules still contain references to the former combined Pipeline B/C contracts; those are retained temporarily so the next Codex refactor can remove them explicitly rather than silently changing behavior during migration.

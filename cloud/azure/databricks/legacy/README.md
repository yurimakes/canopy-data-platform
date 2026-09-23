# Legacy Databricks workloads

This directory preserves Databricks workloads whose current canonical deployment status has not yet been confirmed.

Current preserved groups:

- `canopy-final-trip-5dt024/`
- `canopy-gps-streaming/`
- `canopy-personal-stack-5dt024/`
- `integrated-mode-segmentation/`
- `weekly/`

These directories are intentionally outside `bundles/` and are not included by the canonical ingestion or production-trip bundle configurations.

Before promoting anything from `legacy/` back into `bundles/`, confirm its current workspace deployment, owner, dependencies, and whether another canonical workload has superseded it.

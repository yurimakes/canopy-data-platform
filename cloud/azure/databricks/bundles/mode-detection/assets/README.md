# Runtime assets

This directory is synchronized with the Databricks bundle.

## Model artifact

Expected path:

`assets/models/aihub_canonical_raw120.joblib`

Authoritative source:

`aletheia-ops/canopy-mobility-model-runtime/models/mobility_recognition/aihub_canonical_raw120.joblib`

Git blob SHA of the authoritative source:

`eb85ee8231fb40ac7392df81a8a0b2ded2e0cadd`

The GitHub connector used to build this branch cannot safely copy the 4.55 MB binary payload, so the model file is intentionally not fabricated here. Stage the exact artifact before bundle deployment.

## Transit runtime

`assets/reference-model` contains the minimal transit-context runtime subset copied from the current production-trip implementation:

- transit resolver
- evidence functions
- spatial index
- settings/config
- canonical mode mapping used by the resolver

## Transit reference CSVs

Expected under `assets/transit/`:

- `seoul_bus_stops.csv`
- `seoul_bus_route_stops.csv`
- `subway_stations.csv`
- `korail_stations.csv`

These files are not tracked in the current source repository. They must be staged from their authoritative runtime source before deployment. The mode-detection runtime deliberately falls back to ML-only behavior when reference tables are absent, but transit-equivalence testing requires all four files.

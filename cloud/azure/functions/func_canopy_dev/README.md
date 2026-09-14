# func-canopy-dev deployment source

This directory represents the shared deployment unit for Azure Function App `func-canopy-dev`.

Current Functions:

- `health`
- `gps_smoke`
- `cosmos_smoke`
- `keyvault_smoke`
- `GpsIngest`
- `carbon-smoke` (carbon policy/calculator integration validation endpoint)

## Deployment rule

Deploy this directory as the whole `func-canopy-dev` Function App.

Do not publish only one Function component directly to `func-canopy-dev`, because an app-level deployment can omit existing Functions from the deployed package.

The standalone `GpsIngest` implementation and tests remain under:

`cloud/azure/functions/gps_ingest/`

Before future deployments, verify that the shared app version and standalone GPS ingestion behavior remain aligned.

## Carbon calculation policy

Runtime source of truth:

- `carbon_policy.yaml`
- `carbon_calculator.py`

Key rules:

- segment distance input is `distance_m` and is converted to km before calculation
- `user_confirmed_mode` overrides `predicted_mode` when present
- a correction triggers full recalculation; an old `emission_kgco2e` value is never reused
- walk and human-powered bike are `0 kgCO2e` within the Canopy MVP operational-use boundary
- motorcycle, e-bike and e-scooter are not supported in the current MVP
- factor version: `2026_v1`
- policy version: `carbon-policy-v1`

`carbon-smoke` exists only to validate the Functions integration with the shared policy/calculator. The final client-facing Trip result contract is implemented in the separate Trip result API task.

Local validation command:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_carbon_calculator.py
```

Expected result for this change: `9 passed`.

## Verified on 2026-09-14 before carbon policy deployment

- Five Functions registered in `func-canopy-dev`
- `GpsIngest` returned HTTP 202
- Event Hubs Capture created a new Avro file
- Migration verification event found in Capture: 1/1
- Temporary duplicate Function App `func-canopy-gps-dev` deleted

The `carbon-smoke` Azure deployment/call verification is intentionally recorded separately after this branch is deployed.

No secrets, Function keys, GPS coordinates, or user/device identifiers are stored here.

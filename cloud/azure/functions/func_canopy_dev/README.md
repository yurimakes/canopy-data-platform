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

## Azure identity rule

Canopy Azure-to-Azure connections use Managed Identity/RBAC.

- Function → Event Hubs: Function System Assigned Managed Identity
- Function → Cosmos DB: `DefaultAzureCredential` → Function System Assigned Managed Identity
- Function → Key Vault: `DefaultAzureCredential` → Function System Assigned Managed Identity
- Event Hubs Capture → ADLS: Event Hubs Namespace System Assigned Managed Identity
- ADF → ADLS: ADF System Assigned Managed Identity
- Databricks → ADLS: Access Connector Managed Identity

This carbon calculation change does not introduce any Azure connection string, account key, Cosmos key, Event Hubs SAS key, or Key Vault secret into source code.

The HTTP Function key used to invoke a `FUNCTION`-auth test endpoint is request authentication for the HTTP endpoint only. It is not used for Azure resource-to-resource authentication. Azure resource access remains Managed Identity based.

## Carbon calculation policy

Runtime source of truth:

- `carbon_policy.yaml`
- `carbon_calculator.py`

Key rules:

- segment distance input is `distance_m` and is converted to km before calculation
- carbon calculation currently uses **`predicted_mode` only**
- user confirmation/correction is intentionally **not applied** until the team agrees on that policy
- if `user_confirmed_mode` is present in input, the calculator ignores it for now and still uses `predicted_mode`
- a previously stored `emission_kgco2e` value is never reused as an input to the calculation
- walk and human-powered bike are `0 kgCO2e` within the Canopy MVP operational-use boundary
- motorcycle, e-bike and e-scooter are not supported in the current MVP
- factor version: `2026_v1`
- policy version: `carbon-policy-v1`

The reusable production implementation for this WBS is `carbon_policy.yaml` + `carbon_calculator.py`.

`carbon-smoke` in `function_app.py` is an integration-validation route that proves the deployed Function App can load and execute the same shared policy/calculator. It is **not** the final client-facing Trip result API. Because `func-canopy-dev` is the development Function App and existing smoke endpoints are already kept there, `carbon-smoke` may remain after validation; no cleanup code change is required to close this WBS.

The final client-facing Trip result endpoint will be implemented in the separate `Trip 결과와 탄소 계산 Functions API` task and will call the same calculator. That later task will therefore modify `function_app.py` again, but it does not replace or invalidate this WBS implementation.

## Local validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_carbon_calculator.py
```

Expected result for this change: `10 passed`.

## Azure deployment + verification

From this directory, after `az login`, run:

```powershell
.\scripts\deploy_and_verify_carbon.ps1
```

The script:

1. selects the Canopy subscription
2. runs the 10 carbon tests
3. publishes the whole `func-canopy-dev` deployment unit
4. confirms the carbon Function is registered
5. calls `carbon-smoke`
6. verifies expected emissions and policy/version fields

If the script completes successfully, no post-test code change is required for this WBS. Record the Azure PASS evidence, then the PR can be reviewed/merged according to the team process.

## Verified on 2026-09-14 before carbon policy deployment

- Five Functions registered in `func-canopy-dev`
- `GpsIngest` returned HTTP 202
- Event Hubs Capture created a new Avro file
- Migration verification event found in Capture: 1/1
- Temporary duplicate Function App `func-canopy-gps-dev` deleted

The `carbon-smoke` Azure deployment/call verification is intentionally recorded separately after this branch is deployed.

No secrets, Function keys, GPS coordinates, or user/device identifiers are stored here.

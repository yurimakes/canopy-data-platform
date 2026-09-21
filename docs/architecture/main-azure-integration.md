# Main Azure integration — 2026-09-21

## Repository boundaries

- `canopy-data-platform`, branch `5dt024/main-azure-integration`: mobile UI, account/API, Cosmos adapters, reward settlement, Function deployment and mobile environment.
- `canopy-databricks-pipelines`, branch `5dt024/final-trip-weekly-bundles`: Bundle definitions and ingestion/segment/final Trip/Weekly execution. Existing teammate pipeline sources and folder structure remain unchanged.
- The Function package no longer imports files from `cloud/azure/pipelines`. Pure mission calculation and GPS quality helpers used by the API are under `apps/api/services`; these contain no Spark, Job or Lakeflow wiring. They retain the previously validated calculation rules.

## Production path

App → `func-canopy-dev` → Event Hubs → existing ingestion/ML → Final Trip → Cosmos → API → app.

`CANOPY_FEATURE_CONTAINERS=true` makes the app read the published Weekly generation from Cosmos, not ADLS paths. Account, history, quotes, settlement, missions, ranking and notifications use the existing `canopy-db` containers. A pre-trip KTDB quote and the weekly baseline context are frozen at departure. The API's recovery timer settles completed Trips idempotently without requiring users to open the result screen.

`TRIP_DATABRICKS_DISPATCH_MODE=resident` prevents the API from submitting the obsolete temporary/per-Trip Job. The main host and owned Final Trip Job are configured explicitly. This integration does not modify upstream pipeline resources.

The legacy `users/me/missions` and `users/me/ranking` principal-based handlers remain admin-only when community mode is enabled. The mobile app uses the authenticated `/api/community` projection; their prior 401 responses are not missing app features. Diagnostic endpoints are likewise not mobile-accessible.

## Deployment and rollback

`tools/azure/deploy_main_api.py --apply` packages the integrated Functions and runtime reference assets, preserves all existing function names, backs up current settings and packages, and deploys to the explicitly pinned main subscription. Flex Consumption uses ARM OneDeploy with a read-only, expiring source SAS and remote Linux build. No secrets are printed or committed. Documentation: https://learn.microsoft.com/azure/azure-functions/deployment-zip-push

Backups, receipts and private mobile configuration are in ignored `.local-data/main-review/main-api/`. `/api/health` exposes a source release digest so deployment completion is checked against the intended package rather than any healthy old instance.

Use `Start-MainAzure.ps1` for Expo. `Start-IosBuild.ps1` loads the main configuration and rejects a different host. EAS `production` uses its own production environment; both production and preview are updated to main. `Start-AzureE2E.ps1` remains an explicitly named legacy temporary-account launcher.

## Validation boundary

- App: 81 tests passed; TypeScript check passed.
- API/domain/package: 93 local tests passed using the repository Python/module paths.
- An isolated copy containing only the Git index passed all 82 API/domain/package tests in `Test-AppIntegration.ps1`, confirming that the deployable API does not depend on uncommitted local pipeline experiments.
- Main API: login/profile, community panels and Trip history return 200; real KTDB quote returns a positive baseline; foreign-user GPS is rejected before Event Hubs; mission event retries are idempotent and unauthorized role/mission access is rejected.
- No new GPS Trip, Databricks Job, pipeline update or Weekly test was started for this integration, as requested. Existing running resources were not stopped.
- Full live GPS-to-Weekly acceptance, pipeline latency, scheduled rollover and physical iPhone background capture are not re-certified by this integration. App store submission/build is not executed by this change.

The historical local pipeline experiments remain outside this integration commit. Databricks deployment changes must be made in the separate Bundle repository.

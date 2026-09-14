# func-canopy-dev deployment source

This directory represents the shared deployment unit for Azure Function App `func-canopy-dev`.

Current Functions:

- `health`
- `gps_smoke`
- `cosmos_smoke`
- `keyvault_smoke`
- `GpsIngest`

## Deployment rule

Deploy this directory as the whole `func-canopy-dev` Function App.

Do not publish only one Function component directly to `func-canopy-dev`, because an app-level deployment can omit existing Functions from the deployed package.

The standalone `GpsIngest` implementation and tests remain under:

`cloud/azure/functions/gps_ingest/`

Before future deployments, verify that the shared app version and standalone GPS ingestion behavior remain aligned.

## Verified on 2026-09-14

- Five Functions registered in `func-canopy-dev`
- `GpsIngest` returned HTTP 202
- Event Hubs Capture created a new Avro file
- Migration verification event found in Capture: 1/1
- Temporary duplicate Function App `func-canopy-gps-dev` deleted

No secrets, Function keys, GPS coordinates, or user/device identifiers are stored here.

# Weekly mission v1 deployment contract

Date: 2026-09-16

## Runtime flow

```text
canonical ready Trips
  -> Databricks build_mission_profile.py
  -> ADLS Gold mission_profile history
  -> Cosmos mission-profiles latest snapshot
  -> mission_policy.yaml + mission_engine.py
  -> Azure Functions mission_assignment_api.py
  -> Cosmos mission-assignments
  -> GET /api/users/me/missions?week=YYYY-MM-DD
```

The client GET is lazy/idempotent: if the requested week's deterministic assignment does not exist yet, the endpoint attempts to issue it from the immediately previous completed profile and then returns the stored assignment. `POST /api/users/me/missions/assign` remains available for explicit issue/integration tests.

## Required Azure configuration

Function App settings:

- `CANOPY_COSMOS_ENDPOINT` (or existing `COSMOS_ENDPOINT`)
- `CANOPY_COSMOS_DATABASE` (or existing `COSMOS_DATABASE`; default `canopy-db`)
- `CANOPY_COSMOS_MISSION_PROFILE_CONTAINER` (default `mission-profiles`)
- `CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER` (default `mission-assignments`)
- `CANOPY_CAMPAIGN_ID`
- `CANOPY_CAMPAIGN_TIMEZONE` (default `Asia/Seoul` for current MVP)
- `CANOPY_ALLOW_DEV_USER_HEADER=false` in deployed environments

Databricks settings additionally use:

- `CANOPY_CONFIRMED_TRIPS_PATH`
- `CANOPY_GOLD_MISSION_PROFILE_PATH`
- `CANOPY_GOLD_WEEKLY_USER_PATH`

## Cosmos containers

Two containers are expected unless the deployment later adopts a shared-container convention:

1. `mission-profiles`
2. `mission-assignments`

Both contracts use partition key `/pk`, where:

```text
pk = campaign_id + ':' + user_id
```

Latest mission profile ID:

```text
mission-profile-latest:{campaign_id}:{user_id}
```

Weekly assignment ID is a deterministic UUIDv5 derived from:

```text
campaign_id + user_id + week_start
```

This makes concurrent/repeated assignment requests converge on one Cosmos item. `create_item` is used rather than unconditional upsert so an already-issued weekly assignment is not silently replaced.

## Authentication

The production route expects the authenticated user from Azure Easy Auth's `x-ms-client-principal` header. A direct `X-Canopy-User-Id` header is accepted only when `CANOPY_ALLOW_DEV_USER_HEADER=true` and is intended for local/integration testing, not production.

The Function still uses `FUNCTION` auth at the Azure Functions layer. Per-user identity and ownership come from Easy Auth principal claims.

## Week boundary

Policy week is campaign-local Monday 00:00 inclusive to next Monday 00:00 exclusive. The API normalizes `week=YYYY-MM-DD` to that Monday. Databricks converts those local midnights to UTC before filtering canonical Trip timestamps.

For `Asia/Seoul`:

```text
2026-09-07 00:00 KST -> 2026-09-06 15:00 UTC
2026-09-14 00:00 KST -> 2026-09-13 15:00 UTC
```

## Data contract caveat: zero-Trip participants

The current confirmed-Trip batch only enumerates users who have at least one ready Trip. Therefore a campaign participant with no Trip at all will have no mission profile document. The assignment API deliberately maps that state to `collecting` rather than inventing zero-valued behavior.

If product/analytics later require an explicit Gold `collecting` row for every zero-Trip participant, the campaign participant roster must become the left-side population source for the profile job.

## Primary mode rule

Canonical Trip documents currently persist segment `model_prediction`, not a durable Trip-level primary mode. Mission profile v1 therefore derives the Trip primary mode as the mode with the unique greatest sum of segment distance. Exact ties and invalid/missing segment distances are excluded from the valid denominator and retained in `invalid_trip_reasons`.

This is intentionally conservative and versioned as part of mission profile v1; a future canonical Trip-level primary-mode contract should replace this derivation rather than silently changing it.

## Verification gates before WBS completion

Code gate:

- 20 mission policy cases pass
- profile aggregation tests pass
- Function App and mission modules compile in GitHub Actions

Azure integration gate:

- both Cosmos containers exist with partition key `/pk`
- Function Managed Identity has required Cosmos data access
- Databricks job writes Gold mission profile and latest Cosmos profile
- repeated assignment for the same user/campaign/week returns the same `assignment_id`
- first GET returns or lazily issues the same stored assignment
- iPhone mission screen reads the same assignment

Do not mark the WBS API/profile tasks fully complete until the Azure integration gate has PASS evidence.

# Mission v3.2 validation result — 2026-09-16

## 기준

- Repository: `aletheia-ops/canopy-data-platform`
- Mission v3.2 merge baseline: `b70d5b847fad107d8ef18f6c8beb6adcd26df0f8`
- Validation campaign: `mission-e2e-20260916`
- Warm test user: `mission-e2e-warm-001`
- Source week: `2026-09-07` ~ `2026-09-14` (`2026-W37`)
- ADLS validation root: `abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/`

## 완료된 검증

### 1. Azure 연결 및 권한

- Function App system-assigned Managed Identity → `cosmos-canopy-dev`: 기존 Cosmos native RBAC write/read 검증 PASS.
- Databricks Access Connector: `ac-dbw-canopy-dev`.
- Access Connector MI → `canopy-db/mission-state`: `Cosmos DB Built-in Data Contributor` 컨테이너 scope 부여 완료.
- Databricks Unity Catalog Service Credential: `5dt1team-ac-dbw-canopy-service-credential` 생성 완료.
- Databricks Serverless notebook에서 `dbutils.credentials.getServiceCredentialsProvider(...)`로 `mission-state`에 test item upsert/read 실행 결과 `PASS`.
- Databricks → ADLS Storage Credential / External Location 연결은 기존 검증 PASS.

### 2. Weekly Summary test-path isolation

`build_weekly_summary.py` 실행 복사본을 Workspace에 올리고 import한 뒤 아래 경로를 확인했다.

```text
confirmed_trips:
.../test/mission_e2e/confirmed_trips/

weekly user:
.../test/mission_e2e/weekly_summary_user/

weekly campaign:
.../test/mission_e2e/weekly_summary_campaign/
```

운영 `confirmed_trips` / `gold/weekly_summary_*` 경로를 사용하지 않는 상태에서 검증했다.

### 3. 기본 4-Trip deterministic fixture

입력:

| Trip | 대표 이동 | 거리 | 기대 fact |
| --- | --- | ---: | --- |
| T1 | car | 1.5km | car + short-car |
| T2 | car | 4km | car |
| T3 | bus | 5km | transit + low-carbon |
| T4 | walk | 1km | low-carbon |

결과 PASS:

```text
week                               = 2026-W37
trip_count                         = 4
total_distance_m                   = 11500
total_kg_co2e                      = 1.30
valid_primary_trip_count           = 4
invalid_primary_trip_count         = 0
ambiguous_primary_trip_count       = 0
invalid_segment_primary_trip_count = 0
car_primary_trip_count             = 2
transit_primary_trip_count         = 1
low_carbon_trip_count              = 2
short_car_trip_count               = 1
car_primary_ratio                  = 0.5
short_car_share                    = 0.5
```

### 4. Primary-mode tie fixture

T5:

```text
car 1km + bus 1km
```

대표 이동수단을 임의 선택하지 않고 tie로 제외되는 것을 확인했다.

결과 PASS:

```text
trip_count                   = 5
valid_primary_trip_count     = 4
invalid_primary_trip_count   = 1
ambiguous_primary_trip_count = 1
car_primary_trip_count       = 2
transit_primary_trip_count   = 1
low_carbon_trip_count        = 2
short_car_trip_count         = 1
```

### 5. Invalid segment fixture 및 발견 버그

T6:

```text
walk 500m
+ model_prediction = NULL, distance = 300m
```

최초 실행에서는 Spark SQL의 NULL 3-valued logic 때문에 `~col.isin(...)`이 `NULL`을 invalid로 판정하지 못했고, T6가 잘못된 정상 walk Trip으로 계산되었다.

최초 오동작 증거:

```text
trip_count                         = 6
valid_primary_trip_count           = 5
invalid_primary_trip_count         = 1
ambiguous_primary_trip_count       = 1
invalid_segment_primary_trip_count = 0
low_carbon_trip_count              = 3
car_primary_ratio                  = 0.4
```

수정:

```python
invalid_segment = (
    F.col("effective_mode").isNull()
    | ~F.col("effective_mode").isin(MODES)
    | F.col("distance_m").isNull()
    | (F.col("distance_m") <= 0)
)
```

수정 후 재실행 결과 PASS:

```text
trip_count                         = 6
valid_primary_trip_count           = 4
invalid_primary_trip_count         = 2
ambiguous_primary_trip_count       = 1
invalid_segment_primary_trip_count = 1
car_primary_trip_count             = 2
transit_primary_trip_count         = 1
low_carbon_trip_count              = 2
short_car_trip_count               = 1
car_primary_ratio                  = 0.5
short_car_share                    = 0.5
```

T5/T6는 primary-mode fact에서는 invalid이지만 Trip 자체의 전체 거리/탄소 합계에는 유지한다.

### 6. Mission Profile Serverless E2E

Databricks Serverless에서 `run_mission_profile_serverless.py`를 사용해 named Unity Catalog Service Credential을 직접 주입하고, 위 Weekly User Gold를 Mission Profile 입력으로 사용했다.

결과 PASS:

```text
type                  = mission_profile
profile_version       = mission-profile-v3
profile_status        = ready
user_id               = mission-e2e-warm-001
campaign_id           = mission-e2e-20260916
source_week_start     = 2026-09-07
source_week_end       = 2026-09-14
effective_week_start  = 2026-09-14
valid_trip_count      = 4
invalid_trip_count    = 2
invalid_trip_reasons  = {primary_mode_tie: 1, invalid_segment: 1}
car_primary_trip_count= 2
car_ratio             = 0.5
short_car_trip_count  = 1
short_car_share       = 0.5
transit_primary_trip_count = 1
low_carbon_trip_count = 2
carbon_change_rate    = null
```

`carbon_change_rate=null`은 test path에 직전 주 Weekly Summary가 없기 때문에 의도된 결과다.

ADLS Delta 검증:
- `.../test/mission_e2e/mission_profile/`에 해당 user/source week row 1건 생성 확인.
- Python profile과 ADLS row의 핵심 필드 일치 확인.

Cosmos latest projection 검증:
- container: `canopy-db/mission-state`
- id: `mission-profile-latest:mission-e2e-20260916:mission-e2e-warm-001`
- pk: `mission-e2e-20260916:mission-e2e-warm-001`
- `profile_status=ready`
- Cosmos `profile_hash`와 Python profile `profile_hash` 일치(`HASH MATCH: True`).

따라서 아래 흐름은 실환경 PASS로 판정한다.

```text
Weekly User Gold
→ Databricks Serverless Mission Profile
→ ADLS mission_profile history
→ Cosmos mission-state latest projection
```

## Git 보완

- `build_weekly_summary.py`: NULL `effective_mode`를 명시적 invalid segment로 처리.
- `test_mission_profile_contract.py`: Weekly Summary source contract에 NULL-mode guard를 추가해 회귀를 방지.
- `run_mission_profile_serverless.py`: Serverless named Service Credential 실행 entrypoint 추가.
- `test_mission_profile_serverless_runner.py`: credential name fail-fast 및 Cosmos factory 주입/원복 회귀 검증 추가.

## 아직 완료되지 않은 E2E 게이트

1. Function App에 최신 Mission v3.2 배포.
2. cold-start GET → 4 starter missions.
3. same-week repeated GET → 동일 bundle/idempotency.
4. warm-start GET → 행동 Profile 기반 template 선택.
5. Mission Progress/Response → `mission_response_weekly` → next Mission Profile 통합 검증.

따라서 현재 판정은 **Weekly Summary + Mission Profile + ADLS/Cosmos projection E2E PASS, Function API 및 Mission Response 통합 E2E는 진행 중**이다.

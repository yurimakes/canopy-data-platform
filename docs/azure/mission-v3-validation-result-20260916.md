# Mission v3.2 validation result — 2026-09-16

## 기준

- Repository: `aletheia-ops/canopy-data-platform`
- Mission v3.2 merge baseline: `b70d5b847fad107d8ef18f6c8beb6adcd26df0f8`
- Validation campaign: `mission-e2e-20260916`
- Warm test user: `mission-e2e-warm-001`
- Cold test user: `mission-e2e-cold-20260917-001`
- Source week: `2026-09-07` ~ `2026-09-14` (`2026-W37`)
- Assignment week: `2026-09-14` ~ `2026-09-21`
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

### 7. Function App Mission Assignment API E2E

2026-09-17 `func-canopy-dev`에 최신 Mission v3.2 Function 코드를 전체 ZIP remote build로 배포했다. Azure runtime은 Python 3.13이며 배포 후 `mission_get`이 `/api/users/me/missions`로 등록된 것을 확인했다.

Mission 검증 설정:

```text
CANOPY_CAMPAIGN_ID=mission-e2e-20260916
CANOPY_ALLOW_DEV_USER_HEADER=true
CANOPY_COSMOS_DATABASE=canopy-db
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER=mission-state
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER=mission-state
CANOPY_CAMPAIGN_TIMEZONE=Asia/Seoul
```

기존 smoke용 `COSMOS_DATABASE=canopy-smoke`는 유지하고 Mission은 `CANOPY_COSMOS_DATABASE=canopy-db`를 우선 사용하도록 분리했다.

#### Cold-start

Profile이 없는 `mission-e2e-cold-20260917-001`에 대해 최초 GET 결과 PASS:

```text
status                  = assigned
idempotent              = false
campaign_id             = mission-e2e-20260916
week_start              = 2026-09-14
week_end                = 2026-09-21
policy_version          = mission-policy-v3.2
profile_status_at_issue = cold_start
common_target_count     = 1
difficulty_reason       = first_or_missing_result
mission_count           = 4
```

발급 template:

| category | template | target | affinity comparable | difficulty comparable |
| --- | --- | ---: | --- | --- |
| challenge | `challenge_starter` | 1 | false | false |
| habit | `habit_starter` | 1 | false | false |
| easy_win | `easy_starter` | 1 | false | false |
| explore | `explore_starter` | 1 | false | false |

각 assignment에 발급 시점 `completion_rule` snapshot이 포함된 것을 확인했다.

같은 사용자/같은 주차를 다시 GET한 결과:

```text
idempotent          = true
bundle_id same      = true
assignment_ids same = true
mission_count       = 4
```

Cosmos `mission-state` 조회 결과 해당 cold user/week의 `mission_bundle`은 정확히 1건이었다. API와 Cosmos의 `bundle_id`, `profile_status_at_issue=cold_start`, `policy_version=mission-policy-v3.2`가 일치했다.

#### Warm-start

앞 단계에서 생성한 `mission-e2e-warm-001`의 current Profile을 읽은 결과 PASS:

```text
status                  = assigned
profile_status_at_issue = current
policy_version          = mission-policy-v3.2
common_target_count     = 1
difficulty_reason       = first_or_missing_result
mission_count           = 4
```

행동 Profile 기반 template 선택 결과:

| category | template | target | affinity comparable | difficulty comparable |
| --- | --- | ---: | --- | --- |
| challenge | `challenge_car_to_transit` | 1 | true | true |
| habit | `habit_transit_repeat` | 1 | true | true |
| easy_win | `easy_short_active` | 1 | true | true |
| explore | `explore_active` | 1 | false | false |

Cosmos warm bundle linkage 검증:

```text
warm bundle count       = 1
profile_status_at_issue = current
profile_source_week     = 2026-09-07
profile_version         = mission-profile-v3
policy_version          = mission-policy-v3.2
PROFILE HASH MATCH      = true
```

bundle의 `profile_hash`가 최신 Cosmos Mission Profile의 `profile_hash`와 정확히 일치했다. 따라서 발급된 warm bundle이 검증된 current Profile을 실제 입력으로 사용했음을 확인했다.

따라서 아래 API 흐름은 실환경 PASS로 판정한다.

```text
Cold user → starter bundle 4개 → same-week idempotent reuse → Cosmos bundle 1건
Warm user → current Cosmos Profile → 행동 기반 template 4개 → profile hash linkage
```

## Git 보완

- `build_weekly_summary.py`: NULL `effective_mode`를 명시적 invalid segment로 처리.
- `test_mission_profile_contract.py`: Weekly Summary source contract에 NULL-mode guard를 추가해 회귀를 방지.
- `run_mission_profile_serverless.py`: Serverless named Service Credential 실행 entrypoint 추가.
- `test_mission_profile_serverless_runner.py`: credential name fail-fast 및 Cosmos factory 주입/원복 회귀 검증 추가.
- 본 문서에 Serverless Profile E2E와 Function cold/warm/idempotency/Cosmos linkage 증거를 기록.

## 아직 완료되지 않은 E2E 게이트

1. Mission Progress/Response → `mission_response_weekly` → next Mission Profile 통합 검증.

현재 판정은 **Weekly Summary + Mission Profile + ADLS/Cosmos projection + Mission Assignment Function API core E2E PASS**다. 남은 항목은 Mission Progress/Response 결과가 다음 주 Mission Profile로 되먹임되는 통합 경로 검증이다.

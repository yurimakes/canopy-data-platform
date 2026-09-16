# 주간 미션 v3 배포 계약

작성일: 2026-09-16
정책 버전: `mission-policy-v3.1`
프로필 버전: `mission-profile-v3`
데이터 계약: `shared/schemas/mission/mission_data_contract_v1.yaml`

## 최종 실행 흐름

```text
canonical ready Trip
  → Databricks build_weekly_summary.py
  → ADLS Gold weekly_summary_user
  → Databricks build_mission_profile.py
      + ADLS Gold mission_response_weekly 우선
      + Cosmos mission bundle history는 명시적 fallback
  → ADLS Gold mission_profile history
  → Cosmos mission-profiles latest projection
  → mission_policy.yaml + mission_engine.py
  → Azure Functions mission_assignment_api.py
  → Cosmos mission-assignments current mission_bundle
  → GET /api/users/me/missions?week=YYYY-MM-DD
  → Mission Progress
  → ADLS Gold mission_response_weekly
  → 다음 주 Mission Profile
```

Behavior Change는 이 흐름의 입력도 출력도 아니다.

## Cosmos와 ADLS의 역할

Cosmos를 데이터 파이프라인에서 무조건 배제하지 않는다.

Mission에서는 `mission_bundle`이 API 호출 시 Cosmos에서 최초 생성되는 운영 원본이다. 따라서 현재 주 미션 조회, 동시 요청 중복 방지, 진행 상태의 저지연 조회에는 Cosmos가 적절하다.

반면 장기 학습과 주간 분석은 과거 상태가 바뀌지 않아야 하고 재현 가능해야 한다. 따라서 `mission_response_weekly`가 준비된 뒤에는 Mission Profile이 이 ADLS Gold 이력을 우선 읽는다.

전환기에는:

- `CANOPY_GOLD_MISSION_RESPONSE_PATH`가 정상 조회되면 ADLS Gold 사용
- Gold가 아직 없고 `CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=true`이면 Cosmos bundle history 사용
- 실제 사용한 source를 `mission_history_source`에 기록

즉 Cosmos 사용 자체가 문제인 것이 아니라, 운영 현재 상태와 분석 이력의 역할을 구분한다.

## Weekly Gold 공통 행동 사실

Mission Profile은 canonical Trip을 다시 집계하지 않는다. `build_weekly_summary.py`가 다음 fact를 한 번 계산해 Gold에 저장한다.

- `valid_primary_trip_count`
- `ambiguous_primary_trip_count`
- `car_primary_trip_count`
- `transit_primary_trip_count`
- `low_carbon_trip_count`
- `short_car_trip_count`
- `car_primary_ratio`
- `short_car_share`

대표 이동수단은 Trip 안의 segment별 거리 합을 mode별로 구한 뒤 유일한 최댓값을 사용한다. 동률은 임의 결정하지 않는다.

## Mission Profile

입력:

```text
직전 완료 주 Weekly User Gold
+ 과거 Mission Response history
```

출력:

- ADLS Gold `mission_profile` 이력
- Cosmos `mission-profiles` latest projection

핵심 값:

- 이동 행동: car/short-car/transit/low-carbon
- 탄소 변화율
- category affinity (`category_preferences` 필드명은 하위 호환을 위해 유지)
- difficulty state
- family capability
- source/effective week
- mission history source
- profile hash

`category_preferences`는 심리적 선호를 인과 추정하는 값이 아니다. 여러 미션을 동시에 부여하므로 완료 이력은 '이 유형과 잘 맞았던 정도'를 나타내는 affinity 신호로만 해석한다.

## 미션 배정

사용자는 미션을 직접 고르지 않는다. 서버가 매주 네 카테고리에서 하나씩 총 4개를 부여한다.

- challenge: 적극적인 목표 달성
- habit: 서로 다른 날짜에 반복
- easy_win: 부담이 작은 성공 경험
- explore: 한 가지 저탄소 이동 방식 직접 시도

신규 사용자는 profile이 없어도 starter 4개를 받는다.

## 완료 규칙 스냅샷

가장 중요한 계약은 `completion_rule`이다.

Policy가 바뀌더라도 이미 발급된 미션의 완료 조건이 달라지면 안 된다. 따라서 bundle 발급 순간 각 assignment 안에 완료 규칙을 복사해 고정한다.

예:

```json
{
  "assignment_id": "assign_...",
  "mission_template_id": "easy_short_active",
  "mission_name": "2km 이하 걷기·자전거 2번",
  "target_count": 2,
  "completion_rule": {
    "metric": "qualifying_trip_count",
    "accepted_primary_modes": ["walk", "bike"],
    "max_trip_distance_km": 2.0,
    "target_count": 2,
    "dedupe_key": "trip_id",
    "time_window": "assignment_week",
    "source": "canonical_ready_trip"
  }
}
```

Mission Progress는 최신 `mission_policy.yaml`을 다시 해석하지 않고 assignment의 이 snapshot만 사용한다.

## 지원 metric

### `qualifying_trip_count`
조건에 맞는 distinct Trip 수를 센다.

사용 예:
- 2km 이하 걷기/자전거
- 대중교통 이용
- 친환경 이동

### `distinct_day_count`
조건에 맞는 Trip이 존재한 서로 다른 날짜 수를 센다.

사용 예:
- 서로 다른 N일에 친환경 이동
- 서로 다른 N일에 대중교통 이용

### `distinct_mode_count`
조건에 맞는 서로 다른 primary mode 종류 수를 센다.

사용 예:
- 걷기/자전거 중 한 방식 시도
- 버스/철도 중 한 방식 시도

## 난이도

비교 가능한 미션은 사용자별 `common_target_count`를 사용한다.

```text
첫 주/이력 없음          → 1
직전 비교가능 미션 전부 완료 → +1
일부 완료                → 유지
모두 미완료              → -1
최소                      → 1
최대                      → 5
```

실제 행동 기회가 목표보다 적으면 해당 assignment target을 기회 수로 낮출 수 있다. 이때 공통 목표와 달라지면 affinity 비교에서 제외한다.

Explore처럼 metric 성격상 1회 체험이 적절한 미션은 fixed target을 사용할 수 있다.

## 중복 progress 원칙

- 동일 assignment 안에서는 `trip_id` 중복 집계 금지
- 서로 다른 metric의 여러 assignment가 같은 Trip으로 함께 진척되는 것은 허용
- 이는 '미션 하나를 고르는 게임'이 아니라 여러 행동 목표를 동시에 보여주는 제품 정책에 따른 것
- affinity는 인과적 선호로 해석하지 않음

## Cosmos 컨테이너

현재 계약:

1. `mission-profiles`
2. `mission-assignments`

partition key:

```text
/pk
pk = campaign_id + ':' + user_id
```

latest profile id:

```text
mission-profile-latest:{campaign_id}:{user_id}
```

bundle id seed:

```text
campaign_id + user_id + week_start
```

assignment id seed:

```text
campaign_id + user_id + week_start + category_id
```

같은 주 반복 호출은 동일 bundle로 수렴한다.

## 인증

운영 API는 Azure Easy Auth의 `x-ms-client-principal`에서 user id를 읽는다.

`X-Canopy-User-Id`는 `CANOPY_ALLOW_DEV_USER_HEADER=true`일 때만 통합 테스트용으로 허용한다.

Azure 자원 접근은 `DefaultAzureCredential` + Managed Identity/RBAC을 유지한다.

## 필요한 환경 설정

Function App:

- `CANOPY_COSMOS_ENDPOINT` 또는 `COSMOS_ENDPOINT`
- `CANOPY_COSMOS_DATABASE` 또는 `COSMOS_DATABASE`
- `CANOPY_COSMOS_MISSION_PROFILE_CONTAINER`
- `CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER`
- `CANOPY_CAMPAIGN_ID`
- `CANOPY_CAMPAIGN_TIMEZONE`
- `CANOPY_ALLOW_DEV_USER_HEADER`

Databricks:

- `CANOPY_GOLD_WEEKLY_USER_PATH`
- `CANOPY_GOLD_MISSION_PROFILE_PATH`
- `CANOPY_GOLD_MISSION_RESPONSE_PATH`
- `CANOPY_COSMOS_ENDPOINT`
- `CANOPY_COSMOS_DATABASE`
- `CANOPY_COSMOS_MISSION_PROFILE_CONTAINER`
- `CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER`
- `CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK`

## 스키마

- `shared/schemas/mission/mission_profile.schema.json`
- `shared/schemas/mission/mission_bundle.schema.json`
- `shared/schemas/mission/mission_progress.schema.json`
- `shared/schemas/mission/mission_response_weekly.schema.json`
- `shared/schemas/mission/mission_data_contract_v1.yaml`
- `shared/schemas/baseline/weekly_user_gold.schema.json`

## WBS 완료 게이트

코드:

- Mission policy + service contract tests PASS
- Mission Profile tests PASS
- Function/Databricks modules compile PASS
- 신규 사용자 4개 starter bundle 생성
- 반복 GET idempotency
- bundle 안 completion_rule snapshot 존재
- Policy 수정 후에도 기존 bundle completion_rule 불변

Weekly Gold/Profile:

- 실제 Weekly Gold에 primary behavior fact 생성
- Profile이 Weekly Gold를 읽어 생성
- ADLS mission_profile write
- Cosmos latest profile read-back
- `mission_history_source` 확인

API/Cosmos:

- 두 container `/pk` 확인
- Function Managed Identity read/create 권한 확인
- 신규 사용자 GET
- 같은 주 재조회 동일 bundle id
- concurrent GET 시 bundle 하나로 수렴

Progress/다음 주 학습:

- assignment의 completion_rule snapshot만 사용
- 같은 Trip retry 중복 증가 없음
- 주 밖 Trip 제외
- 완료 시점 idempotent
- mission_response_weekly Gold 생성
- 다음 주 Profile에서 Gold history 우선 사용
- 완료된 comparable category만 positive evidence 반영

이 게이트가 모두 PASS되기 전까지 Profile/API WBS를 최종 완료로 표시하지 않는다.

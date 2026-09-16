# 주간 미션 v3 배포 계약

작성일: 2026-09-16
정책 버전: `mission-policy-v3.2`
프로필 버전: `mission-profile-v3`
데이터 계약: `shared/schemas/mission/mission_data_contract_v1.yaml`

## 최종 실행 흐름

```text
canonical ready Trip
  → Databricks build_weekly_summary.py
  → ADLS Gold weekly_summary_user
  → Databricks build_mission_profile.py
      + ADLS Gold mission_response_weekly 우선
      + Cosmos mission bundle history는 명시적 전환기 fallback
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

## Cosmos와 ADLS 역할

Cosmos를 데이터 파이프라인에서 무조건 배제하지 않는다.

Mission에서는 `mission_bundle`이 API 호출 시 Cosmos에서 최초 생성되는 운영 상태의 원본이다. 따라서 현재 주 미션 조회, 동시 요청 중복 방지, 저지연 진행 상태 조회에는 Cosmos가 적절하다.

반면 다음 주 학습과 장기 분석은 과거 상태가 변하지 않아야 하고 재현 가능해야 한다. 따라서 주 마감 후에는 `mission_response_weekly`를 ADLS Gold에 고정하고 Mission Profile이 이를 우선 읽는다.

전환기 fallback 정책:

- `CANOPY_GOLD_MISSION_RESPONSE_PATH`를 정상 조회하면 ADLS Gold를 사용한다.
- Response Gold가 아직 준비되지 않았고 `CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=true`인 경우에만 Cosmos bundle history를 사용한다.
- fallback 기본값은 `false`다.
- 실제 사용한 source는 profile의 `mission_history_source`에 기록한다.

즉 Cosmos 사용 자체가 문제가 아니라 `현재 운영 상태`와 `마감된 분석 이력`의 역할을 구분하는 것이 핵심이다.

## Weekly Gold 공통 행동 fact

Mission Profile은 canonical Trip을 다시 집계하지 않는다. `build_weekly_summary.py`가 대표 이동수단 관련 사실을 한 번 계산해 Gold에 저장한다.

필수 컬럼:

- `valid_primary_trip_count`
- `invalid_primary_trip_count`
- `ambiguous_primary_trip_count`
- `invalid_segment_primary_trip_count`
- `car_primary_trip_count`
- `transit_primary_trip_count`
- `low_carbon_trip_count`
- `short_car_trip_count`
- `car_primary_ratio`
- `short_car_share`

대표 이동수단 규칙:

1. Trip의 segment를 mode별로 묶는다.
2. mode별 segment distance 합을 계산한다.
3. 유일한 최대 mode만 Trip primary mode로 인정한다.
4. 최대값 동률은 `ambiguous_primary_trip_count`로 기록하고 valid 분모에서 제외한다.
5. 지원하지 않는 mode, distance 누락, distance <= 0 segment가 하나라도 있으면 그 Trip의 primary mode를 무효 처리하고 `invalid_segment_primary_trip_count`로 기록한다.
6. `invalid_primary_trip_count = ambiguous_primary_trip_count + invalid_segment_primary_trip_count`를 만족해야 한다.
7. `short_car_trip_count`는 valid car-primary Trip 중 전체 Trip distance가 2km 이하인 건수다.

## Mission Profile

입력:

```text
직전 완료 주 Weekly User Gold
+ 과거 Mission Response history
```

출력:

- ADLS Gold `mission_profile` 이력
- Cosmos `mission-profiles` latest serving projection

핵심 값:

- car / short-car / transit / low-carbon 행동 fact
- 탄소 변화율
- category affinity (`category_preferences` 필드명은 하위 호환 때문에 유지)
- difficulty state
- family capability
- source/effective week
- mission history source
- profile hash

`category_preferences`는 심리적 선호를 인과 추정하는 값이 아니다. 네 미션을 동시에 부여하고 metric도 다르므로 현재는 `이 유형의 미션과 잘 맞았던 정도`를 나타내는 descriptive affinity로만 저장한다.

`mission-policy-v3.2`에서는 affinity를 실제 배정 우선순위에 사용하지 않는다.

```text
preference_learning.enabled_for_personalization = false
activation_gate = empirical_template_calibration_required
```

실제 사용자 데이터가 충분히 쌓여 template별 기본 난이도 차이를 보정한 뒤 별도 policy version에서 개인화 사용 여부를 결정한다.

## 주간 미션 카테고리

사용자는 미션을 직접 고르지 않는다. 서버가 매주 네 카테고리에서 하나씩 총 4개를 부여한다.

- `challenge`: 평소보다 한 단계 더 적극적인 이동
- `habit`: 서로 다른 날짜에 반복
- `easy_win`: 짧고 부담이 작은 성공 경험
- `explore`: 새로운 저탄소 이동수단 한 가지 경험

현재 대표 template:

### Challenge

- 자동차 이력이 있으면: `3km 이상 대중교통 이동 {target_count}번 도전`
- 저탄소 이동 이력이 있으면: `2km 이상 걷기·자전거 이동 {target_count}번 도전`
- cold start: `2km 이상 친환경 이동 {target_count}번 도전`

### Habit

- 대중교통 이력이 있으면: `서로 다른 {target_count}일에 대중교통 이용하기`
- 그 외 저탄소 이력이 있으면: `서로 다른 {target_count}일에 친환경 이동하기`
- cold start: `서로 다른 {target_count}일에 친환경 이동 시작하기`

### Easy Win

- short-car 기회가 있으면: `2km 이하 걷기·자전거 {target_count}번`
- 그 외: `가장 편한 친환경 이동 1번`
- cold start: `가장 편한 친환경 이동 1번`

### Explore

- short-car 기회가 있으면: `걷기·자전거 중 한 가지 방식으로 이동해 보기`
- 자동차 이력이 있으면: `버스·철도 중 한 가지 방식으로 이동해 보기`
- cold start: `친환경 이동수단 한 가지 직접 이용해 보기`

카테고리 이름만 다르고 실제 행동이 같은 미션이 동시에 노출되지 않도록 metric과 거리 조건을 분리한다.

## 완료 규칙 snapshot

이미 발급한 미션은 이후 policy가 바뀌어도 판정 기준이 바뀌면 안 된다. 따라서 bundle 발급 순간 각 assignment 안에 `completion_rule`을 복사해 고정한다.

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

Mission Progress는 최신 `mission_policy.yaml`을 다시 해석하지 않고 발급된 assignment의 snapshot만 사용한다.

## 지원 progress metric

### `qualifying_trip_count`
조건에 맞는 distinct Trip 수.

사용 예:
- 3km 이상 대중교통
- 2km 이상 걷기/자전거
- 2km 이하 걷기/자전거

### `distinct_day_count`
조건에 맞는 Trip이 존재한 서로 다른 날짜 수.

사용 예:
- 서로 다른 N일에 친환경 이동
- 서로 다른 N일에 대중교통 이용

### `distinct_mode_count`
조건에 맞는 서로 다른 primary mode 종류 수.

사용 예:
- 걷기/자전거 중 한 방식 경험
- 버스/철도 중 한 방식 경험

거리 조건은 `min_trip_distance_km`와 `max_trip_distance_km`를 snapshot에서 읽는다.

## affinity와 difficulty comparability 분리

기존 `preference_comparable` 하나가 affinity 학습과 난이도 조정 두 역할을 동시에 하던 문제를 제거했다.

- `affinity_comparable`: descriptive affinity evidence에 포함할 수 있는지
- `difficulty_comparable`: 다음 주 adaptive common target 조정에 포함할 수 있는지
- `preference_comparable`: 기존 bundle 하위 호환을 위해 `affinity_comparable` alias로만 유지

fixed target 또는 기회 ceiling 때문에 common target과 다른 assignment는 다음 주 difficulty 조정에서 제외할 수 있다.

## adaptive 난이도

다음 주 adaptive mission의 `common_target_count`는 다음 규칙을 사용한다.

```text
첫 주/이력 없음               → 1
직전 difficulty-comparable 전부 완료 → +1
일부 완료                     → 유지
전부 미완료                   → -1
최소                           → 1
최대                           → 5
```

Explore 및 일부 Easy Win처럼 metric 특성상 고정 목표가 적절한 미션은 `fixed_target_count=1`을 사용하고 adaptive difficulty 비교에서 제외한다.

## 중복 progress 원칙

- 동일 assignment 안에서는 같은 `trip_id`를 중복 집계하지 않는다.
- 같은 Trip이 서로 다른 metric의 여러 assignment를 동시에 진척시키는 것은 허용한다.
- late Trip update가 들어오면 assignment를 idempotent하게 재계산할 수 있어야 한다.
- 완료 후 같은 Trip이 재처리되어도 completion event가 중복 생성되면 안 된다.

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

같은 사용자·캠페인·주차의 반복 또는 동시 GET은 하나의 bundle로 수렴해야 한다.

## 인증

운영 API는 Azure Easy Auth의 `x-ms-client-principal`에서 user id를 읽는다.

`X-Canopy-User-Id`는 `CANOPY_ALLOW_DEV_USER_HEADER=true`일 때만 통합 테스트용으로 허용한다.

HTTP trigger auth level은 `FUNCTION`이다. 직접 curl/Postman 검증 시 Function key가 필요하며 query parameter `code=<FUNCTION_KEY>` 또는 `x-functions-key` header를 사용한다.

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
- `CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK` (기본 `false`)
- `CANOPY_CAMPAIGN_TIMEZONE`

## 스키마

- `shared/schemas/mission/mission_profile.schema.json`
- `shared/schemas/mission/mission_bundle.schema.json`
- `shared/schemas/mission/mission_progress.schema.json`
- `shared/schemas/mission/mission_response_weekly.schema.json`
- `shared/schemas/mission/mission_data_contract_v1.yaml`
- `shared/schemas/baseline/weekly_user_gold.schema.json`

## WBS 완료 게이트

코드 게이트:

- Mission policy + service contract tests PASS
- Mission Profile tests PASS
- Function/Databricks modules compile PASS
- schema JSON/YAML parse PASS

실환경 게이트:

- 실제 Weekly Gold primary behavior fact 검산
- Profile ADLS write + Cosmos latest projection read-back
- cold start GET 4개 starter bundle
- warm start template 적합성
- same-week 및 concurrent GET idempotency
- completion_rule freeze
- Progress가 snapshot contract만 사용
- mission_response_weekly Gold 생성
- 다음 주 Profile이 Response Gold를 우선 읽음
- affinity/difficulty가 각 comparability flag에 맞게 업데이트

실환경 게이트가 끝나기 전까지 Profile/API WBS를 최종 완료로 표시하지 않는다.

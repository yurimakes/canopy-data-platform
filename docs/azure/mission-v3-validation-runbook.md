# Mission v3 검증 Runbook

이 문서는 `fix/mission-v3-service-contract` 브랜치 기준 검증 절차다. **merge 전에 수행**한다.

## 0. 검증 대상

1. Weekly Gold 공통 행동 fact
2. Mission Profile 생성
3. Cosmos latest profile projection
4. Mission GET API cold start / warm start
5. same-week idempotency
6. completion_rule snapshot 고정
7. Mission Progress 연동 준비
8. Mission Response → 다음 주 Profile 학습

## 1. GitHub CI

Draft PR을 열어 `Mission code execution check`가 PASS하는지 확인한다.

PASS 조건:

- Function App / Mission modules / Databricks modules compile
- `test_mission_policy.py`
- `test_mission_service_contract.py`
- `test_build_mission_profile.py`
- `test_mission_profile_contract.py`

FAIL이면 Azure 검증으로 넘어가지 않는다.

## 2. Cosmos 사전 점검

필요 container:

- `mission-profiles`
- `mission-assignments`

두 container의 partition key가 `/pk`인지 확인한다.

문서 pk 규칙:

```text
{campaign_id}:{user_id}
```

Function App 및 Databricks 실행 주체가 필요한 Cosmos RBAC을 갖는지 확인한다.

최소 권한:

- profile latest: read/upsert
- assignment bundle: read/create/query

운영에서는 account key/connection string 대신 Managed Identity를 유지한다.

## 3. Databricks 환경변수/Job parameter

확인 값:

```text
CANOPY_GOLD_WEEKLY_USER_PATH
CANOPY_GOLD_MISSION_PROFILE_PATH
CANOPY_GOLD_MISSION_RESPONSE_PATH
CANOPY_COSMOS_ENDPOINT
CANOPY_COSMOS_DATABASE
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK
CANOPY_CAMPAIGN_TIMEZONE
```

Mission Response가 아직 구현되지 않았다면 검증 단계에서는:

```text
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=true
```

로 둔다.

Mission Response Gold가 준비되면 false로 바꿔 ADLS history만 사용하는 검증을 추가한다.

## 4. Weekly Gold 검증

테스트 campaign/week에 ready Trip을 준비한 뒤 `build_weekly_summary.py` 실행.

확인 컬럼:

```text
valid_primary_trip_count
ambiguous_primary_trip_count
car_primary_trip_count
transit_primary_trip_count
low_carbon_trip_count
short_car_trip_count
car_primary_ratio
short_car_share
```

검산 예:

- car 1.5km 1건
- car 4km 1건
- bus 5km 1건
- walk 1km 1건

기대:

```text
trip_count = 4
valid_primary_trip_count = 4
car_primary_trip_count = 2
short_car_trip_count = 1
transit_primary_trip_count = 1
low_carbon_trip_count = 2
car_primary_ratio = 0.5
short_car_share = 0.5
```

동률 Trip 1건을 추가하면:

```text
ambiguous_primary_trip_count += 1
valid_primary_trip_count에는 포함되지 않음
```

## 5. Mission Profile 검증

직전 완료 주를 source week로 `build_mission_profile.py` 실행.

ADLS `gold/mission_profile`에서 확인:

```text
profile_version = mission-profile-v3
effective_week_start = source_week_end
car_primary_trip_count
short_car_trip_count
transit_primary_trip_count
low_carbon_trip_count
mission_history_source
profile_hash
```

Mission Response Gold가 아직 없으면:

```text
mission_history_source = cosmos_bundle_fallback
```

이 가능하다.

Response Gold가 준비된 뒤에는:

```text
mission_history_source = mission_response_gold
```

를 기대한다.

Cosmos `mission-profiles`에서 다음 id를 조회한다.

```text
mission-profile-latest:{campaign_id}:{user_id}
```

ADLS 결과와 핵심 값/profile_hash가 같은지 확인한다.

## 6. Cold-start API 검증

테스트 환경에서만:

```text
CANOPY_ALLOW_DEV_USER_HEADER=true
```

신규 user id로 호출한다.

```http
GET /api/users/me/missions?week=2026-09-14
X-Canopy-User-Id: mission-e2e-new-user
```

확인:

- status = assigned
- profile_status_at_issue = cold_start
- missions = 4
- category = challenge/habit/easy_win/explore 각각 1개
- assignment마다 completion_rule 존재
- completion_rule.target_count == assignment.target_count
- policy_version = mission-policy-v3.1

## 7. Same-week idempotency

같은 user/week으로 GET을 2회 이상 반복한다.

기대:

- bundle_id 동일
- assignment_id 4개 동일
- mission_name 동일
- completion_rule 동일
- Cosmos bundle 문서는 1개

가능하면 동시 요청 5~10개도 수행한다. `create_item` 충돌 후 기존 문서를 읽어 하나로 수렴해야 한다.

## 8. Warm-start template 검증

예시 Profile:

```text
car_primary_trip_count = 4
short_car_trip_count = 2
transit_primary_trip_count = 2
low_carbon_trip_count = 5
```

다음 주 GET에서 starter 대신 조건에 맞는 template이 선택되는지 확인한다.

예상 예:

- challenge → short active 또는 transit challenge
- habit → low carbon distinct-day mission
- easy_win → short active easy mission
- explore → active mode explore

실제 선택은 priority와 eligibility에 따른다.

## 9. completion_rule freeze 검증

1. 특정 주 bundle을 발급한다.
2. branch에서 policy 문구/규칙을 임시 변경한 테스트 빌드를 만든다.
3. 같은 주 GET을 다시 호출한다.

기대:

- 기존 bundle 반환
- 기존 completion_rule 불변
- 기존 mission_name 불변

다음 주 신규 bundle만 새 policy를 사용해야 한다.

## 10. Mission Progress 담당자 handoff 검증

Progress 구현은 `mission_policy.yaml`을 다시 읽어 완료 조건을 만들면 안 된다.

반드시:

```text
mission_bundle.missions[].completion_rule
```

을 읽는다.

필수 케이스:

- 같은 trip_id 재처리 → progress 증가 없음
- week 밖 Trip → 증가 없음
- accepted_primary_modes 불일치 → 증가 없음
- max distance 초과 → 증가 없음
- distinct_day_count → 같은 날 여러 Trip이어도 1일
- distinct_mode_count → 같은 mode 여러 Trip이어도 1종류
- 완료 후 같은 Trip retry → 완료 이벤트 중복 없음

## 11. Mission Response 검증

주 마감 후 assignment마다 1행을 `mission_response_weekly` Gold에 생성한다.

완료뿐 아니라 미완료 assignment도 반드시 남긴다.

필수 값:

```text
campaign_id
user_id
week_start
week_end
bundle_id
assignment_id
mission_template_id
mission_family
category_id
difficulty_band
common_target_count
target_count
preference_comparable
progress_count
achievement_rate
completed
linked_trip_count
policy_version
response_version
```

## 12. 다음 주 학습 검증

예: 직전 주 comparable 미션에서 challenge만 완료.

다음 Profile에서:

```text
challenge.positive_evidence_count += 1
미완료 category는 감소하지 않음
```

Explore처럼 `preference_comparable=false`인 미션은 완료해도 affinity evidence에 넣지 않는다.

난이도:

- comparable 전부 완료 → common target +1
- 일부 완료 → 유지
- 전부 미완료 → -1
- 범위 1~5

## 13. 최종 PASS 기준

다음이 모두 PASS하면 Profile/API WBS를 완료 처리할 수 있다.

- CI PASS
- Weekly Gold fact 검산 PASS
- Profile ADLS write PASS
- Cosmos latest profile read-back PASS
- cold start PASS
- warm start PASS
- same-week idempotency PASS
- completion_rule freeze PASS
- Progress contract PASS
- Mission Response Gold PASS
- next-week affinity/difficulty learning PASS

Progress/Response가 아직 팀원 작업 중이면 Profile/API는 `구현 완료 / 통합 검증 대기`로 유지한다.

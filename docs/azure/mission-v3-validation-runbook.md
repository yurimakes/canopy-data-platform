# Mission v3.2 검증 Runbook

이 문서는 `fix/mission-v3-service-contract` / Draft PR #28 기준 검증 절차다. **모든 PASS 증거를 남기기 전 merge하지 않는다.**

정책 버전: `mission-policy-v3.2`
프로필 버전: `mission-profile-v3`

---

## 0. 검증 원칙과 테스트 식별자

운영 campaign/user를 사용하지 않는다. dev 환경에서 검증 전용 값을 사용한다.

권장 예:

```text
TEST_CAMPAIGN_ID = mission-e2e-20260916
COLD_USER_ID      = mission-e2e-cold-001
WARM_USER_ID      = mission-e2e-warm-001
SOURCE_WEEK_START = 2026-09-07
SOURCE_WEEK_END   = 2026-09-14
MISSION_WEEK      = 2026-09-14
```

검증 증거로 최소한 다음을 저장한다.

```text
검증 시각
Git branch
Git HEAD
campaign_id
user_id
week
Databricks job/run id
Function request/response JSON
Cosmos 문서 id
PASS/FAIL
실패 시 error/log 위치
```

테스트가 끝난 뒤 검증용 Cosmos 문서와 test Delta path는 팀 정책에 따라 삭제하거나 `mission-e2e-*` prefix로 보존한다.

---

## 1. GitHub 코드 게이트

### 1-1. PR 상태

GitHub → `aletheia-ops/canopy-data-platform` → Pull requests → PR #28을 연다.

확인:

```text
Draft = true
Merged = false
base = main
head = fix/mission-v3-service-contract
```

### 1-2. Actions

PR의 Checks 또는 Actions에서 다음 두 workflow를 확인한다.

```text
Mission code execution check = PASS
Baseline code execution check = PASS
```

Mission PASS 범위:

- Function App / Mission module / Databricks module compile
- Mission policy tests
- Mission service contract tests
- Mission Profile tests
- Mission Profile contract tests
- Mission JSON schema parse
- Mission YAML/data contract parse

Baseline PASS 범위:

- `build_weekly_summary.py` 변경에 의한 기존 Baseline 회귀 없음

FAIL이면 Azure 검증으로 넘어가지 않는다.

---

## 2. Cosmos 사전 점검

Azure Portal → Cosmos DB account → Data Explorer.

필요 container:

```text
Database: canopy-db (환경 설정이 다르면 실제 값 사용)
Container: mission-profiles
Container: mission-assignments
```

### 2-1. Partition key

각 container → Scale & Settings 또는 container 설정에서 partition key를 확인한다.

기대:

```text
/pk
```

문서의 실제 partition key 값:

```text
{campaign_id}:{user_id}
```

예:

```text
mission-e2e-20260916:mission-e2e-cold-001
```

`/campaign_id`, `/user_id` 등으로 만들어져 있으면 **검증 중단**. 코드 계약과 다르다.

### 2-2. Managed Identity / RBAC

Function App의 System Assigned Managed Identity가 활성화되어 있는지 확인한다.

Function에 필요한 data-plane 권한:

```text
mission-profiles     : read
mission-assignments  : read + create
```

Databricks Mission Profile job에 필요한 권한:

```text
mission-profiles     : upsert
mission-assignments  : query (Cosmos history fallback을 켤 때만)
```

Account key/connection string을 코드에 직접 넣지 않는다. 현재 코드는 `DefaultAzureCredential`을 사용한다.

권한 오류의 대표 증상:

```text
403 Forbidden
Request blocked by authorization
```

이 경우 코드 수정보다 먼저 Azure Identity/RBAC을 확인한다.

---

## 3. 환경 설정 확인

### 3-1. Function App

Azure Portal → Function App → Settings / Environment variables(또는 Configuration).

확인:

```text
CANOPY_COSMOS_ENDPOINT
CANOPY_COSMOS_DATABASE
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER
CANOPY_CAMPAIGN_ID
CANOPY_CAMPAIGN_TIMEZONE
CANOPY_ALLOW_DEV_USER_HEADER
```

통합 테스트 동안에만:

```text
CANOPY_CAMPAIGN_ID=mission-e2e-20260916
CANOPY_CAMPAIGN_TIMEZONE=Asia/Seoul
CANOPY_ALLOW_DEV_USER_HEADER=true
```

운영 복귀 시 반드시:

```text
CANOPY_ALLOW_DEV_USER_HEADER=false
```

### 3-2. Databricks

Mission Profile job/cluster에서 다음 값을 확인한다.

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

정상 운영 기본값:

```text
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=false
```

Mission Response가 아직 팀원 작업 중이라 Gold 자체가 존재하지 않는 전환기 검증에서만 임시로:

```text
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=true
```

를 사용한다.

주의: fallback은 배선 검증을 위한 것이다. Cosmos bundle의 `completed/progress`가 실제 Progress 처리로 갱신되지 않는 환경에서는 fallback만으로 다음 주 학습 성공을 검증할 수 없다.

---

## 4. Weekly Gold deterministic fixture 검증

목적: Mission Profile이 사용할 공통 행동 fact가 Trip과 정확히 일치하는지 검산한다.

가능하면 기존 운영 confirmed Trip path가 아니라 **dev test Delta path**를 사용한다.

예:

```text
abfss://curated@<storage>.dfs.core.windows.net/test/mission_e2e/confirmed_trips/
abfss://curated@<storage>.dfs.core.windows.net/test/mission_e2e/weekly_summary_user/
abfss://curated@<storage>.dfs.core.windows.net/test/mission_e2e/weekly_summary_campaign/
```

Weekly Summary test job에서 해당 test path를 사용하도록 설정한 뒤 아래 Trip을 준비한다.

### 4-1. 기본 4 Trip

`WARM_USER_ID`에 다음 ready Trip을 준비한다.

| Trip | primary mode | distance | 기대 분류 |
|---|---|---:|---|
| T1 | car | 1.5km | car + short-car |
| T2 | car | 4.0km | car |
| T3 | bus | 5.0km | transit + low-carbon |
| T4 | walk | 1.0km | low-carbon |

각 Trip은 최소한 다음 canonical field를 가진다.

```text
trip_id
user_id
campaign_id
status=ready
ended_at
updated_at
carbon.kg_co2e
carbon.policy_version
carbon.factor_version
carbon.unit=kgCO2e
segments[].model_prediction
segments[].distance_m
segments[].carbon_kg
```

### 4-2. Weekly Summary 실행

기존 Databricks Workflow가 있으면 해당 dev Job의 `build_weekly_summary.py` task에 다음 parameter를 넣는다.

```text
campaign_id = mission-e2e-20260916
week_start  = 2026-09-07
week_end    = 2026-09-14
```

Run now → Parameters 확인 → 실행.

### 4-3. Gold 확인

Databricks SQL 또는 notebook에서 실제 test Gold path로 조회한다.

```sql
SELECT
  user_id,
  campaign_id,
  week,
  trip_count,
  valid_primary_trip_count,
  invalid_primary_trip_count,
  ambiguous_primary_trip_count,
  invalid_segment_primary_trip_count,
  car_primary_trip_count,
  transit_primary_trip_count,
  low_carbon_trip_count,
  short_car_trip_count,
  car_primary_ratio,
  short_car_share
FROM delta.`<CANOPY_GOLD_WEEKLY_USER_PATH>`
WHERE campaign_id = 'mission-e2e-20260916'
  AND user_id = 'mission-e2e-warm-001';
```

기대:

```text
trip_count                         = 4
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

### 4-4. 동률 Trip 추가

T5에 segment를 다음처럼 둔다.

```text
car 1km
bus 1km
```

다시 Weekly Summary를 실행한다.

기대:

```text
trip_count = 5
valid_primary_trip_count = 4
invalid_primary_trip_count = 1
ambiguous_primary_trip_count = 1
invalid_segment_primary_trip_count = 0
```

T5는 car/bus/low-carbon count에 들어가면 안 된다.

### 4-5. invalid segment Trip 추가

T6 예:

```text
segment 1: walk, 500m
segment 2: model_prediction 누락 또는 distance_m <= 0
```

다시 실행.

기대:

```text
trip_count = 6
valid_primary_trip_count = 4
invalid_primary_trip_count = 2
ambiguous_primary_trip_count = 1
invalid_segment_primary_trip_count = 1
```

**한 잘못된 segment를 버리고 남은 segment만으로 primary mode를 정하면 FAIL**이다.

---

## 5. Mission Profile 생성 검증

### 5-1. 전환기 fallback 모드

Mission Response Gold가 아직 없다면 Databricks test environment에서만:

```text
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=true
```

설정.

### 5-2. Profile job 실행

`build_mission_profile.py` task에:

```text
campaign_id       = mission-e2e-20260916
source_week_start = 2026-09-07
source_week_end   = 2026-09-14
```

을 넣고 실행한다.

### 5-3. ADLS Profile 확인

```sql
SELECT *
FROM delta.`<CANOPY_GOLD_MISSION_PROFILE_PATH>`
WHERE campaign_id = 'mission-e2e-20260916'
  AND user_id = 'mission-e2e-warm-001'
  AND source_week_start = '2026-09-07';
```

확인:

```text
profile_version       = mission-profile-v3
source_week_start     = 2026-09-07
source_week_end       = 2026-09-14
effective_week_start  = 2026-09-14
car_primary_trip_count
short_car_trip_count
transit_primary_trip_count
low_carbon_trip_count
mission_history_source
profile_hash
```

Weekly Gold의 행동 count와 Profile의 count가 같아야 한다.

### 5-4. Cosmos latest projection 확인

Cosmos → `mission-profiles` → New SQL Query.

```sql
SELECT * FROM c
WHERE c.id = 'mission-profile-latest:mission-e2e-20260916:mission-e2e-warm-001'
```

확인:

```text
pk = mission-e2e-20260916:mission-e2e-warm-001
profile_hash = ADLS row의 profile_hash
source/effective week = ADLS와 동일
행동 count = ADLS와 동일
```

ADLS는 생성됐지만 Cosmos가 없으면 Profile 계산은 PASS가 아니라 **projection FAIL**로 기록한다.

---

## 6. Function 배포/브랜치 확인

PR은 merge하지 않으므로 검증 Function이 `fix/mission-v3-service-contract` 코드를 배포했는지 확인한다.

배포한 commit SHA를 검증 기록에 남긴다.

검증 대상 policy:

```text
mission-policy-v3.2
```

기존 main/PR #24 코드가 배포되어 `mission-policy-v3`가 반환되면 이번 PR 검증이 아니다.

---

## 7. Cold-start API 검증

### 7-1. Function key 준비

route의 auth level이 `FUNCTION`이므로 테스트 호출에 Function key가 필요하다.

Azure Portal → Function App → Functions → 해당 HTTP function → Function Keys에서 test key를 확인하거나 별도 test key를 사용한다.

키는 Git/문서/스크린샷에 남기지 않는다.

### 7-2. 완전 신규 사용자 사용

Cosmos `mission-profiles`와 `mission-assignments`에 `COLD_USER_ID` 문서가 없는지 먼저 확인한다.

### 7-3. 호출

PowerShell 예:

```powershell
$base = "https://<FUNCTION_APP_HOST>/api/users/me/missions"
$headers = @{
  "x-functions-key" = "<FUNCTION_KEY>"
  "X-Canopy-User-Id" = "mission-e2e-cold-001"
}
Invoke-RestMethod -Method GET `
  -Uri "$base?week=2026-09-14" `
  -Headers $headers | ConvertTo-Json -Depth 20
```

curl 예:

```bash
curl -sS \
  -H "x-functions-key: <FUNCTION_KEY>" \
  -H "X-Canopy-User-Id: mission-e2e-cold-001" \
  "https://<FUNCTION_APP_HOST>/api/users/me/missions?week=2026-09-14"
```

### 7-4. 기대값

```text
status = assigned
bundle.policy_version = mission-policy-v3.2
bundle.profile_status_at_issue = cold_start
missions.length = 4
category = challenge, habit, easy_win, explore 각 1개
모든 assignment에 completion_rule 존재
completion_rule.target_count = assignment.target_count
assignment_id 4개 모두 서로 다름
```

cold-start 대표 문구도 직접 확인한다.

```text
challenge → 2km 이상 친환경 이동 1번 도전
habit     → 서로 다른 1일에 친환경 이동 시작하기
easy_win  → 가장 편한 친환경 이동 1번
explore   → 친환경 이동수단 한 가지 직접 이용해 보기
```

---

## 8. Same-week idempotency 검증

같은 user/week으로 GET을 최소 3회 반복한다.

각 응답을 저장해 비교한다.

기대:

```text
bundle_id 동일
assignment_id 4개 동일
mission_template_id 동일
mission_name 동일
completion_rule 동일
policy_hash 동일
```

Cosmos `mission-assignments`에서:

```sql
SELECT * FROM c
WHERE c.campaign_id = 'mission-e2e-20260916'
  AND c.user_id = 'mission-e2e-cold-001'
  AND c.week_start = '2026-09-14'
  AND c.type = 'mission_bundle'
```

기대 문서 수 = 1.

### 8-1. 동시성

가능하면 동일 GET을 동시에 5~10번 호출한다.

PowerShell 간단 예:

```powershell
1..10 | ForEach-Object -Parallel {
  Invoke-RestMethod -Method GET `
    -Uri "https://<FUNCTION_APP_HOST>/api/users/me/missions?week=2026-09-14" `
    -Headers @{
      "x-functions-key" = "<FUNCTION_KEY>"
      "X-Canopy-User-Id" = "mission-e2e-concurrent-001"
    }
} -ThrottleLimit 10
```

모든 응답이 동일 `bundle_id`로 수렴하고 Cosmos 문서가 1개면 PASS.

---

## 9. Warm-start template 검증

5단계에서 만든 `WARM_USER_ID`의 latest Profile을 사용한다.

GET:

```text
week=2026-09-14
X-Canopy-User-Id=mission-e2e-warm-001
```

`profile_status_at_issue=current`를 기대한다.

행동 fact 예:

```text
car_primary_trip_count > 0
short_car_trip_count > 0
transit_primary_trip_count > 0
low_carbon_trip_count > 0
```

v3.2에서 예상 가능한 template:

```text
challenge → challenge_car_to_transit 우선
habit     → habit_transit_repeat 우선
Easy      → easy_short_active 우선
Explore   → explore_active 우선
```

각 template의 eligibility와 priority 때문에 실제 Profile 값에 따라 달라질 수 있다.

중요 확인:

- Challenge/Habit/Easy/Explore가 단순히 같은 목표의 문구 변형이 아닌지
- distance/day/mode metric이 의도대로 분리되는지
- `affinity_comparable`과 `difficulty_comparable`이 assignment에 존재하는지
- `preference_comparable == affinity_comparable`인지(하위 호환 alias)

---

## 10. adaptive target 검증

Profile의 `difficulty_state`를 이용해 다음 케이스를 확인한다.

### A. 처음

```text
previous target 없음 → common_target_count = 1
```

### B. difficulty-comparable 전부 완료

```text
last_common_target_count = 1
last_comparable_mission_count = 3
last_completed_comparable_count = 3
```

기대:

```text
common_target_count = 2
```

### C. 일부 완료

```text
3개 중 1~2개 완료 → target 유지
```

### D. 모두 미완료

```text
이전 target 2 → 다음 target 1
```

### E. 상한

```text
이전 target 5 + 전부 완료 → 5 유지
```

fixed target Easy/Explore는 `difficulty_comparable=false`여야 하며 adaptive target 분모에 들어가면 안 된다.

---

## 11. completion_rule freeze 검증

이 검증은 이미 발급된 미션이 정책 변경으로 바뀌지 않는지 확인한다.

1. `freeze-user-001`, week `2026-09-14` bundle을 발급한다.
2. 응답 JSON의 `mission_name`, `policy_version`, `policy_hash`, `completion_rule`을 저장한다.
3. test branch/build에서 한 template의 문구 또는 distance rule을 임시 변경한다. **main에는 merge하지 않는다.**
4. 같은 Cosmos DB와 같은 user/week로 GET한다.
5. 기존 bundle이 반환되는지 비교한다.

PASS:

```text
bundle_id unchanged
mission_name unchanged
completion_rule unchanged
기존 bundle policy_version/hash unchanged
```

그 다음 새로운 week/user로 발급했을 때만 새 policy를 받아야 한다.

---

## 12. Mission Progress 담당자 handoff 검증

Progress 구현은 최신 `mission_policy.yaml`을 다시 읽어 완료 조건을 만들면 안 된다.

유일한 판정 기준:

```text
mission_bundle.missions[].completion_rule
```

필수 케이스:

### qualifying_trip_count

- accepted mode + 거리조건 만족 distinct Trip → +1
- 같은 `trip_id` retry → +0
- `min_trip_distance_km` 미달 → +0
- `max_trip_distance_km` 초과 → +0
- assignment week 밖 → +0
- `status != ready` → +0

### distinct_day_count

예: 월요일 같은 날에 qualifying Trip 5개.

기대:

```text
progress_count = 1일
```

화요일 qualifying Trip 추가:

```text
progress_count = 2일
```

캠페인 timezone(`Asia/Seoul`) 기준 날짜를 사용한다.

### distinct_mode_count

walk 5회:

```text
progress_count = 1종류
```

bike 추가:

```text
progress_count = 2종류
```

### completion idempotency

`progress_count >= target_count`가 되는 최초 순간 completed=true.

같은 Trip을 재처리하거나 late update가 와도 완료 이벤트가 중복 생성되면 안 된다.

---

## 13. Mission Response Gold 검증

주 마감 후 **완료와 미완료를 포함해 assignment마다 정확히 1행**을 만든다.

조회:

```sql
SELECT *
FROM delta.`<CANOPY_GOLD_MISSION_RESPONSE_PATH>`
WHERE campaign_id = 'mission-e2e-20260916'
  AND user_id = '<TEST_USER_ID>'
  AND week_start = '2026-09-14'
ORDER BY category_id;
```

한 bundle이면 기대 row 수 = 4.

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
affinity_comparable
difficulty_comparable
preference_comparable  # affinity alias
progress_count
achievement_rate
completed
linked_trip_count
policy_version
response_version
```

체크:

```text
assignment_id unique
completed=false 행도 존재 가능하며 누락되면 안 됨
policy_version = 해당 bundle이 발급된 policy version
```

---

## 14. ADLS history 우선 사용 검증

Mission Response Gold가 생성된 뒤:

```text
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK=false
```

로 바꾼다.

다음 주 Profile job을 실행한다.

예:

```text
source_week_start = 2026-09-14
source_week_end   = 2026-09-21
```

기대:

```text
mission_history_source = mission_response_gold
```

이 상태에서 Cosmos `mission-assignments` query 권한을 제거해도 Profile history 계산이 가능해야 한다(단, Profile latest upsert 권한은 별개).

Response Gold가 없거나 접근 불가한데 fallback=false라면 job은 조용히 빈 history로 진행하면 안 되고 **실패해야 한다**. 이것도 PASS 조건이다.

---

## 15. 다음 주 affinity 학습 검증

예: 직전 주 assignment 결과를 다음처럼 만든다.

```text
challenge: completed=true,  affinity_comparable=true
habit:     completed=false, affinity_comparable=true
easy_win:  completed=true,  affinity_comparable=false
explore:   completed=true,  affinity_comparable=false
```

다음 Mission Profile의 `category_preferences_json` 확인.

기대:

```text
challenge positive_evidence_count += 1
habit     증가 없음 / 감점 없음
easy_win  증가 없음
explore   증가 없음
```

현재 affinity는 분석용이며 template 배정 priority를 바꾸는 데 사용하지 않는다.

---

## 16. 다음 주 difficulty 학습 검증

직전 주에서 `difficulty_comparable=true`인 assignment만 본다.

예:

```text
challenge true/completed
habit     true/completed
easy_win  false
eexplore  false
```

두 comparable mission이 모두 완료됐다면 다음 common target은 +1.

반대로 fixed-target Easy/Explore의 완료 여부 때문에 common target이 오르거나 내려가면 FAIL.

---

## 17. 인증 복귀 검증

통합 검증이 끝나면 Function App에서:

```text
CANOPY_ALLOW_DEV_USER_HEADER=false
```

로 되돌린다.

그 후 임의의 `X-Canopy-User-Id`만 넣어 호출했을 때 401이 나오는지 확인한다.

실제 앱 인증/Easy Auth principal에서는 정상 user id를 읽어야 한다.

---

## 18. 최종 PASS 체크리스트

아래를 모두 체크한 뒤에만 PR을 merge 후보로 본다.

```text
[ ] Draft PR 유지 / 아직 merge 안 함
[ ] Mission CI PASS
[ ] Baseline CI PASS
[ ] Cosmos mission-profiles /pk PASS
[ ] Cosmos mission-assignments /pk PASS
[ ] Function Managed Identity/RBAC PASS
[ ] Weekly Gold 4-Trip 검산 PASS
[ ] primary tie exclusion PASS
[ ] invalid segment exclusion PASS
[ ] Mission Profile ADLS write PASS
[ ] Cosmos latest profile projection PASS
[ ] cold-start 4 category PASS
[ ] policy_version = mission-policy-v3.2
[ ] same-week idempotency PASS
[ ] concurrent GET single-bundle convergence PASS
[ ] warm-start template selection PASS
[ ] affinity/difficulty comparability 분리 PASS
[ ] adaptive target 1~5 PASS
[ ] completion_rule freeze PASS
[ ] Progress dedupe/week/mode/distance PASS
[ ] distinct-day PASS
[ ] distinct-mode PASS
[ ] completion idempotency PASS
[ ] mission_response_weekly 4 rows PASS
[ ] Response Gold 우선 + fallback=false PASS
[ ] next-week affinity learning PASS
[ ] next-week difficulty learning PASS
[ ] CANOPY_ALLOW_DEV_USER_HEADER=false 복귀 PASS
```

Progress/Response가 아직 팀원 구현 중이라 12~16단계를 수행할 수 없다면:

```text
Mission template/policy: 구현 + 코드 검증 완료
Mission Profile: 구현 완료 / 실환경 E2E 검증 진행 중
Mission API: 구현 완료 / 실환경 E2E 검증 진행 중
Mission Progress/Response 연계: 팀원 구현 대기
```

으로 표시하고 WBS 전체를 최종 COMPLETE로 올리지 않는다.

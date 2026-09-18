# CANOPY Weekly Pipeline / Reward Ledger 트러블슈팅

- 기준일: 2026-09-18
- 기준 브랜치: `feature/materialize-reward-ledger`
- 관련 PR: #54
- 범위: Weekly Pipeline, Reward Ledger, Ranking, Cosmos serving, Azure Function Ranking API, iOS Ranking adapter

> 형식: 문제 → 원인 → 해결 → 검증 → 재발 방지 / 남은 위험

---

## 1. Weekly Pipeline Ranking이 0행으로 생성됨

### 문제

Lakeflow Pipeline 자체는 성공하고 `ranking` Materialized View도 생성됐지만 결과 row가 0건이었다.

### 원인

`weekly_pipeline.ranking()`은 canonical Reward Ledger History 경로를 읽는다.

```text
gold/reward_ledger_history
```

하지만 해당 canonical Delta가 아직 materialize되지 않은 상태였다.

`_read_optional_delta()`는 `PATH_NOT_FOUND`일 때만 typed 0-row DataFrame으로 fallback하므로 Pipeline 자체는 실패하지 않고 Ranking만 0행이 될 수 있다.

### 해결

Reward Ledger materialization 로직을 먼저 sandbox target에서 검증하고, 실제 Cosmos reward row로 `build_ranking()`까지 별도 런타임 검증했다.

### 검증

- Cosmos reward rows: 3
- paid 2 / adjusted 1
- total points: 180
- 테스트 사용자 A: 100 points / rank 1
- 테스트 사용자 B: 80 points / rank 2

### 남은 위험

**canonical `gold/reward_ledger_history`는 아직 작성하지 않았다.**

따라서 weekly pipeline의 실제 `ranking()`을 완성하려면 Reward Ledger canonical materialization 실행 순서를 연결해야 한다.

---

## 2. Reward Ledger materialization을 canonical Gold에 바로 쓰기 어려움

### 문제

처음부터 canonical Gold에 쓰면 팀 공유 경로를 오염시킬 수 있어 안전한 검증이 필요했다.

### 원인

Reward Ledger는 Cosmos의 실제 지급/조정 기록을 Delta 이력으로 materialize해야 하므로 write 검증이 필요하다.

### 해결

`GOLD_REWARD_LEDGER_HISTORY_TARGET`에서 `table:<catalog.schema.table>` 형식을 지원하도록 하고 sandbox managed table을 검증 대상으로 사용했다.

검증 target:

```text
dbw_canopy_dev.sandbox.reward_ledger_history
```

### 검증

동일 campaign/week를 두 번 동기화해도:

- row_count = 3
- paid = 2
- adjusted = 1
- total_points = 180

결과가 동일했다.

즉 campaign/week partition re-sync idempotency를 확인했다.

### 남은 위험

sandbox 검증 성공은 canonical Gold write 성공과 동일하지 않다.

canonical 경로에 실제 write하기 전:

- 권한
- schema
- partition overwrite 범위
- 실행 순서
- downstream Ranking/Campaign KPI

를 다시 검증해야 한다.

---

## 3. Reward Ledger Cosmos 자격증명 경로 불일치

### 문제

기존 `reward_ledger.py`는 다음 secret scope를 먼저 찾는다.

```text
canopy-scope / cosmos-endpoint
canopy-scope / cosmos-key
```

실제 현재 Databricks 환경에서는 해당 secret을 사용할 수 없었다.

### 원인

코드의 과거 secret 가정과 현재 팀 공용 Cosmos 연결 설정이 다르다.

기존 Campaign Membership Job은 별도의 현재 팀 secret scope/key 설정을 사용하고 있었다.

### 해결

런타임 validator에서는 기존 팀 Job 설정을 읽어 현재 사용 중인 Cosmos endpoint/secret 설정을 재사용했다.

새 secret scope를 만들지 않았다.

### 검증

실제 dev Cosmos Reward Ledger read/write 성공.

### 남은 위험

**`reward_ledger.py::_get_container()` 자체는 아직 과거 `canopy-scope` 우선 로직을 유지한다.**

따라서 canonical 운영 경로 연결 전 이 부분을 현재 팀 인증 방식으로 정리해야 한다.

가능하면:

- Databricks의 기존 팀 secret 설정 재사용 또는
- 승인된 Managed Identity 방식

중 하나로 통일하고 새 자격증명 리소스를 임의 생성하지 않는다.

---

## 4. Databricks Web Terminal에서 Spark 실행 실패

### 문제

Web Terminal에서 Spark 기반 validator를 실행할 때 `CONNECT_URL_NOT_SET` 계열 오류가 발생했다.

### 원인

Databricks Web Terminal의 일반 Python 프로세스는 Spark session / Lakeflow execution context에 자동 연결되지 않는다.

### 해결

작업 용도를 분리했다.

```text
Web Terminal
- git
- 일반 Python
- 비-Spark Cosmos 확인

Run File / Notebook / Job
- Spark
- Delta
- Unity Catalog
- dbutils
```

### 검증

Run File에서 Reward Ledger → Delta → Ranking Spark validator가 성공했다.

### 재발 방지

Spark 코드를 Web Terminal에서 억지로 실행하지 않는다.

Databricks Connect는 필요한 경우에만 별도 도입한다.

---

## 5. Run File에서 `ModuleNotFoundError: azure.cosmos`

### 문제

Spark Run File 실행 시 Azure Cosmos SDK import가 실패했다.

### 원인

해당 Databricks compute environment에 Python dependency가 없었다.

### 해결

Environment dependencies에 현재 팀 코드와 맞는 패키지를 추가했다.

```text
azure-cosmos==4.17.0
azure-identity==1.25.3
```

### 검증

이후 실제 Cosmos Reward Ledger validator가 정상 실행됐다.

### 재발 방지

Cosmos를 사용하는 Run File / Job의 environment dependency를 명시적으로 관리한다.

---

## 6. `ranking-snapshots` Cosmos container가 존재하지 않음

### 문제

기존 `publish_ranking_to_cosmos.py`는 기본적으로 `ranking-snapshots` container를 기대했다.

실제 dev Cosmos에는 해당 container가 없었다.

### 원인

코드의 계획된 serving contract와 현재 실제 Cosmos 구조가 일치하지 않았다.

현재 실제 Cosmos에는 `ranking` container가 존재한다.

### 해결

새 Cosmos container를 만들지 않았다.

기존 `ranking` container의 구조를 read-only로 먼저 확인한 뒤 전용 테스트 campaign partition에 points 기반 테스트 문서를 저장했다.

### 검증

- 기존 legacy carbon ranking 문서 유지
- 테스트 points document write/read 성공
- `schema_version = ranking-points-v1`
- `score_unit = points`
- legacy document overwrite = false

### 남은 위험

현재 검증용 points 문서를 운영 serving contract로 확정하면 안 된다.

`publish_ranking_to_cosmos.py`는 여전히 `ranking-snapshots`를 기본 대상으로 한다.

최종 contract는 팀 합의 후 한 구조로 정리해야 한다.

---

## 7. 기존 Ranking schema가 carbon 단위였음

### 문제

기존 `ranking` container의 과거 문서는 `score_kg_co2e` 기반이었다.

현재 Reward Ledger 기반 Ranking은 points 단위다.

### 원인

과거 carbon ranking 설계와 현재 reward points ranking 설계가 공존한다.

### 해결

legacy 문서를 수정하지 않고 테스트 points 문서에 명시적으로:

```text
schema_version = ranking-points-v1
score_unit = points
```

를 저장했다.

iOS Ranking UI도 `carbonKg / kgCO2e` 표시에서 `points / P` 계약으로 수정했다.

### 검증

HTTP Ranking API에서 `score_unit = points`와 100 / 80 points를 확인했다.

### 재발 방지

carbon ranking과 reward points ranking을 같은 필드 의미로 취급하지 않는다.

---

## 8. Department Ranking이 0행

### 문제

runtime validation에서 personal ranking은 생성됐지만 department ranking은 0행이었다.

### 원인

검증용 campaign membership fixture에 `department_id`가 없었다.

`build_ranking()`은 `department_id IS NOT NULL` 사용자만 부서 계산에 포함한다.

### 해결

이번 검증에서는 personal ranking의 정확성을 우선 확인하고 department 0행을 실패로 취급하지 않았다.

### 남은 위험

실제 부서 ranking E2E는 아직 검증되지 않았다.

다음 검증에서는:

- department_id가 있는 membership
- minimum participant 정책
- average_per_member 계산

을 함께 확인해야 한다.

---

## 9. Ranking publisher의 Department contract mismatch

### 문제

`publish_ranking_to_cosmos.py`의 department publisher는:

```python
row["member_user_ids"]
```

를 기대한다.

하지만 현재 `build_ranking()`의 department result는 해당 컬럼을 출력하지 않는다.

### 원인

publisher와 ranking transform 계약이 서로 다른 시점에 작성됐다.

### 해결

이번 runtime serving 검증에서는 기존 publisher를 사용하지 않았다.

### 남은 위험

운영 publisher를 사용하려면 둘 중 하나를 팀 정책에 맞게 수정해야 한다.

- department result에 내부 member list를 안전하게 제공
- publisher가 membership을 별도로 조회해 `is_me` 판단용 정보를 구성

개인정보 노출 방지 기준을 먼저 정한다.

---

## 10. Ranking Azure Function 배포

### 문제

Ranking 결과를 앱이 소비할 HTTP endpoint가 없었다.

### 해결

새 Function App을 만들지 않고 기존 공용 `func-canopy-dev`에 `ranking_get` Blueprint를 추가했다.

공유 Function App 전체 deployment unit을 배포했다.

### 검증

Azure Functions host:

- Running
- 기존 Functions 유지
- `ranking_get` 등록 확인
- 실제 GET 요청 성공

응답 핵심:

```text
status = ready
week = 2026-W38
score_unit = points
personal_count = 2

rank  points
1     100
2      80
```

### 재발 방지

Function 하나만 따로 배포하지 않는다.

`func_canopy_dev` 디렉터리 전체를 shared Function App 배포 단위로 유지한다.

---

## 11. Azure CLI hostname 조회가 빈 값

### 문제

`az functionapp show --query defaultHostName` 결과가 빈 문자열로 반환돼 URI가:

```text
https:///api/...
```

형태가 됐다.

### 원인

배포는 정상인데 해당 CLI query에서 hostname 값을 얻지 못했다.

### 해결

성공한 Azure Functions publish 로그에 출력된 실제 host를 사용해 API를 호출했다.

### 검증

실제 Ranking API HTTP 요청 성공.

### 남은 위험

향후 자동화에서는 hostname 조회 실패 시:

- `hostNames[0]`
- deployment output
- Azure resource metadata

등 fallback을 두되 hardcoded host를 운영 코드에 저장하지 않는다.

---

## 12. PowerShell에서 한국어 nickname이 깨져 보임

### 문제

API 응답의 한국어 nickname 일부가 PowerShell 출력에서 깨져 보였다.

### 원인

응답 자체 실패보다는 PowerShell 콘솔 출력 인코딩 문제로 판단했다.

### 해결

개인정보와 표시 문자열을 제외하고 rank/points/is_me 등 핵심 필드를 별도로 출력해 검증했다.

### 검증

- rank 1 = 100
- rank 2 = 80
- first row `is_me = true`

### 남은 위험

실제 iPhone 화면에서 UTF-8 nickname 렌더링은 아직 확인하지 않았다.

---

## 13. iOS `tsc is not recognized`

### 문제

`npm run typecheck` 실행 시 `tsc`를 찾지 못했다.

### 원인

`apps/ios/node_modules`가 설치되지 않은 상태였다.

### 해결

lockfile 기준:

```powershell
npm ci
npm run typecheck
```

실행.

### 검증

TypeScript `tsc --noEmit` 통과.

### 남은 위험

npm install 과정에서 moderate vulnerability 경고가 존재했다.

이번 Ranking 기능 검증과 직접적인 오류는 아니므로 `npm audit fix --force`를 무작정 적용하지 않는다. dependency 영향 검토 후 별도 처리한다.

---

## 14. iOS Ranking과 Trip/Auth 설정이 섞일 위험

### 문제

기존 iOS 앱에서 `CANOPY_TRIP_API_URL`은 login/Trip API 용도다.

Ranking API 검증을 위해 여기에 Function URL을 억지로 넣으면 account/trip 계약을 깨뜨릴 수 있다.

### 원인

초기 Ranking adapter가 기존 Trip config 재사용을 전제로 하면 서비스 역할이 섞인다.

### 해결

Ranking 전용 설정으로 분리했다.

```text
CANOPY_RANKING_API_URL
CANOPY_RANKING_FUNCTION_KEY
CANOPY_RANKING_CAMPAIGN_ID
CANOPY_RANKING_WEEK
```

또한 개발 검증 전용 `CANOPY_RANKING_E2E` 모드를 추가했다.

### 검증

정적 TypeScript 검사 통과.

### 남은 위험

실제 iPhone/Expo Go runtime UI는 아직 실행하지 않았다.

---

## 15. 실제 iPhone / Expo Go 검증 미실행

### 문제

물리 iPhone에 Expo Go가 설치되어 있지 않아 즉시 device E2E를 수행하지 않았다.

### 결정

후순위로 미뤘다.

현재 완료된 범위:

```text
Cosmos Reward Ledger
→ Ranking transform
→ Cosmos ranking test serving
→ Azure Function API
→ HTTP 100/80 response
→ iOS adapter/typecheck
```

미완료:

```text
Azure Function
→ 실제 iPhone
→ 화면 100 P / 80 P 표시
```

### 재개 조건

최종 데모 전 Expo Go 또는 적절한 개발 빌드 환경에서 1회 확인한다.

---

## 16. `baseline_gold`가 여전히 empty_result

### 문제

Personal / Global Baseline 계산은 연결됐지만 최종 Baseline Gold가 비어 있다.

### 원인

통합 저장 schema만 초안으로 존재하고 실제 조립 로직이 아직 작성되지 않았다.

### 해결 상태

미해결.

### 다음 작업

Personal과 Global의 grain이 다르므로 단순 union하지 않는다.

먼저 앱/후속 계산이 요구하는 Baseline Gold contract를 확정한 뒤 join/struct 구조를 구현한다.

---

## 17. `weekly_user_profile`이 Mission Response를 읽지만 사용하지 않음

### 문제

Mission Response Delta를 읽어 `build_weekly_user_profile(..., mission_df)`에 넘기지만 실제 helper 내부에서:

```python
_ = mission_df
```

로 무시한다.

### 원인

Mission Response weekly contract가 아직 확정되지 않았기 때문이다.

### 해결 상태

의도적 미완료.

### 재발 방지

Mission History가 반영됐다고 표현하지 않는다.

현재 프로필은 Weekly Gold 기반 행동 요약까지만 실제 계산한다.

---

## 18. `next_week_missions`가 실제 미션을 생성하지 않음

### 문제

함수와 Materialized View가 있어 완료처럼 보일 수 있다.

### 실제 코드

```python
return empty_result(
    MISSION_BUNDLE_SCHEMA,
    "weekly_user_profile",
)
```

### 해결 상태

미해결.

### 다음 작업

최신 미션 정책/템플릿 및 profile contract를 확인한 뒤 실제 assignment helper를 연결한다.

---

## 19. Campaign KPI는 계산 코드가 연결됐지만 전체 실값 검증은 미완료

### 문제

`campaign_kpi()`는 구현되어 있지만 일부 upstream 데이터가 0-row fallback일 수 있다.

### 현재 입력

- weekly_gold
- mission_response
- behavior_change
- reward_ledger
- campaign_membership

### 현재 위험

- mission_response canonical 미확정
- reward_ledger canonical 미materialized
- behavior_change는 다주차 기록 부족 시 insufficient_data

### 결론

Campaign KPI **코드 연결은 완료**로 볼 수 있지만 **전체 KPI 실데이터 E2E 완료**라고 표현하면 안 된다.

---

## 20. `weekly_outputs_gold`가 여전히 empty_result

### 문제

전체 Weekly 결과를 앱 소비용으로 묶는 마지막 단계가 placeholder다.

### 실제 코드

```python
return empty_result(
    WEEKLY_OUTPUTS_DRAFT_SCHEMA,
    ...
)
```

### 해결 상태

미해결.

### 다음 작업

앱/API의 실제 소비 단위를 먼저 확정한다.

모든 서로 다른 grain을 한 row에 억지로 struct/array로 넣기보다:

- user-week output
- campaign-week KPI
- ranking snapshot
- mission bundle

을 별도 Gold로 유지하고 Read API에서 조합하는 방식도 함께 검토한다.

---

## 21. Databricks Git Folder 최신화 절차

Run File 전에 branch를 정확히 맞춘다.

```bash
cd /Workspace/canopy-data-platform-git
git fetch origin
git switch feature/materialize-reward-ledger
git reset --hard origin/feature/materialize-reward-ledger
git log -1 --oneline
git status -sb
```

주의:

- 다른 팀원의 미커밋 작업이 있는 shared Git Folder에서는 `reset --hard` 사용 전 영향 범위를 확인한다.
- 개인/전용 Databricks Git Folder에서만 위 절차를 기본으로 사용한다.

---

## 22. 현재 남은 P0 트러블슈팅 포인트

1. `reward_ledger.py` 인증 설정을 현재 팀 방식으로 정리
2. Reward Ledger canonical Gold materialization 연결
3. `baseline_gold` 실제 구현
4. Mission Response weekly contract 확정
5. `next_week_missions` 실제 assignment 연결
6. canonical Ranking row 검증
7. Campaign KPI canonical 실값 검증
8. `weekly_outputs_gold` 실제 output contract 구현

---

## 23. 현재 최종 판단

현재 가장 중요한 성과는 다음 구간이 실제 런타임에서 증명됐다는 점이다.

```text
Reward Ledger actual Cosmos
→ Delta materialization
→ Ranking transform
→ Cosmos serving
→ Azure Function API
```

반면 CANOPY Weekly 전체 목표:

```text
Final Trip
→ Weekly
→ Baseline
→ Behavior
→ Mission
→ Reward
→ Ledger
→ Ranking
→ Campaign KPI
→ App output
```

은 아직 완성되지 않았다.

다음 작업은 새 기능을 넓히기보다 **현재 placeholder와 canonical materialization gap을 제거하는 것**을 최우선으로 한다.

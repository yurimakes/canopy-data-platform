# CANOPY Weekly Pipeline 작업 진행 결과 총정리

- 기준일: 2026-09-18
- 기준 저장소: `aletheia-ops/canopy-data-platform`
- 기준 브랜치: `feature/materialize-reward-ledger`
- 기준 커밋: `259a3b2`
- 관련 PR: #54 `feat: materialize Reward Ledger history`
- Databricks 대상: `dbw-canopy-dev` / `[dev 5dt024] canopy-weekly-analysis-pipeline-dev`
- 핵심 파일: `cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py`

> 이 문서는 계획과 구현 상태를 분리해서 기록한다. 실제 실행 증거가 없는 항목은 완료로 표현하지 않는다.

## 1. weekly_pipeline.py 작업 목표

### 목표 1

`sandbox.final_trips` → Weekly Gold → Baseline / Behavior → Mission 관련 데이터 → Reward → Ledger → Ranking → Campaign KPI → 앱 소비 출력까지 끊김 없이 준비한다.

민철님이 앱 및 최종 E2E를 연결할 때 Weekly 구조를 다시 크게 뜯어고치지 않아도 되는 상태를 목표로 한다.

### 목표 2

Sandbox 데이터 또는 iPhone 실데이터가 들어왔을 때 자격 판정, 미션, 보상, 랭킹이 끝까지 연결되어 계산되는 흐름을 만든다.

### 목표 3

최신 확정 정책과 팀원 코드가 누락되지 않도록 기존 계산 모듈을 Lakeflow 흐름에 연결한다.

---

## 2. 목표 파이프라인

```text
Final Trip Gold
    ↓
Weekly Summary
    ↓
Weekly Gold
    ├─ Baseline Eligibility
    │   ├─ Personal Baseline
    │   ├─ Personal Ready Users
    │   ├─ Global Eligibility
    │   ├─ Global Baseline
    │   └─ Baseline Gold
    │
    ├─ Behavior Change
    │
    ├─ Weekly User Profile
    │   └─ Next Week Missions
    │
    ├─ Reward Calculation / Reward Ledger
    │   └─ Reward Ledger History
    │
    ├─ Ranking
    │
    ├─ Campaign KPI
    │
    └─ Weekly Outputs Gold
            ↓
        API / iOS 소비
```

---

## 3. 상태 기준

- ✅ **구현 + 현재 근거로 검증됨**
- ⚠️ **코드는 연결됐지만 canonical 입력/출력 또는 최종 E2E가 아직 미완료**
- ❌ **현재 코드가 placeholder / empty_result 이거나 실제 계산 연결이 없음**

---

## 4. 현재 전체 작업 현황

| 단계 | 상태 | 현재 확인 내용 | 남은 작업 |
|---|---|---|---|
| `final_trip_gold_input` | ✅ | 개발용 Final Trip Delta에서 최신 ready Trip을 읽는 실제 코드 연결 | 운영 입력 전환 시 경로/계약 재확인 |
| `weekly_summary` | ✅ | Final Trip → 사용자/캠페인/주차별 집계 계산 연결 | 실제 iPhone 장기간 데이터 회귀 테스트 |
| `weekly_gold` | ✅ | Materialized View로 저장되는 실제 Weekly Gold 연결 | 없음 |
| `baseline_eligibility` | ✅ | Weekly Gold + campaign membership 입력 연결, 이전 완료 주만 사용 | collecting 상태는 데이터 기간/정책 조건에 따라 정상 발생 가능 |
| `personal_baseline` | ✅ | 이전 완료 주 누적 기반 Personal Baseline 계산 연결 | 충분한 관찰 기간 데이터 확보 필요 |
| `personal_ready_users` | ✅ | Personal ready 사용자 필터 연결 | 실제 ready 사용자 생성 데이터 확인 |
| `global_eligibility` | ✅ | Global 최소 참여자 조건 판정 연결 | 실제 참여자 수 충족 데이터 확인 |
| `global_baseline` | ✅ | ready Personal Baseline의 동일 사용자 가중 평균 연결 | 실제 ready 상태 런타임 확인 |
| `baseline_gold` | ❌ | 현재도 `empty_result(...)` 반환 | Personal + Global 결과를 실제 저장 계약으로 materialize |
| `behavior_change` | ✅ | 기존 `build_behavior_change()` 연결 | 다주차 데이터 없으면 `insufficient_data`; 인과효과가 아닌 관측 KPI로만 사용 |
| `weekly_user_profile` | ⚠️ | Weekly Gold 기반 프로필 계산은 연결됨 | `mission_df`를 인자로 받지만 현재 실제 계산에서 사용하지 않음 |
| Mission Response history | ⚠️ | Delta 입력 계약/path는 존재 | `mission_response_weekly` 계약 확정 및 실제 생성/소비 연결 필요 |
| `next_week_missions` | ❌ | 현재 `empty_result(MISSION_BUNDLE_SCHEMA, ...)` | 프로필 + 미션 정책 → 실제 다음 주 미션 생성 로직 연결 |
| Reward Ledger 모듈 | ✅ | Cosmos Reward Ledger read/write, adjustment, history sync 및 sandbox runtime 검증 완료 | 아래 canonical weekly 연결은 별도 |
| Reward Ledger canonical Gold | ⚠️ | sandbox Delta materialization은 검증됨 | canonical `gold/reward_ledger_history` materialization을 weekly 흐름에 연결 |
| `ranking` 계산 코드 | ✅ | 기존 `build_ranking()` 실제 Spark 런타임 검증 완료 | canonical Reward Ledger Gold가 있어야 weekly pipeline에서 실데이터 row 생성 |
| `ranking` canonical pipeline 출력 | ⚠️ | Materialized View는 생성 가능 | canonical ledger 입력이 없어 기존 실행에서 0행이었던 원인 해결 필요 |
| Cosmos Ranking serving | ✅ | 기존 `ranking` 컨테이너의 전용 테스트 캠페인 points 문서 write/read 검증 | 운영 contract 확정 전 테스트 serving으로만 취급 |
| Ranking Azure Function API | ✅ | 기존 `func-canopy-dev`에 `ranking_get` 배포 및 HTTP 응답 검증 | 운영 인증/캠페인 정책 정리 |
| iOS Ranking adapter | ⚠️ | points 계약으로 변경, TypeScript `typecheck` 통과 | 실제 iPhone / Expo Go 화면 검증은 후순위 |
| `campaign_kpi` | ⚠️ | Weekly Gold + membership + mission response + behavior + reward 입력 계산 코드 연결 | mission response/canonical ledger가 실제 채워진 상태에서 KPI 값 검증 필요 |
| `weekly_outputs_gold` | ❌ | 현재도 `empty_result(...)` | 최종 앱 소비 구조/저장 계약 확정 후 실제 materialization |
| 전체 canonical Weekly E2E | ❌ | 일부 구간별 E2E는 검증됨 | 위의 baseline/mission/reward canonical/output gaps를 모두 연결해야 완료 |

---

## 5. 2026-09-18 Reward Ledger / Ranking 작업에서 실제 검증된 범위

### 5.1 Reward Ledger sandbox

검증 결과:

- sandbox Reward Ledger history materialization 성공
- 동일 campaign/week 재동기화 후 결과 불변
- `paid`: 2건
- `adjusted`: 1건
- 총 3건
- 총 포인트: 180
- canonical Gold write는 하지 않음

### 5.2 실제 dev Cosmos Reward Ledger

검증 결과:

- 실제 dev Cosmos Reward Ledger read/write 성공
- 지급 2건 + 조정 1건
- 합계 180 points
- 기존 테스트 캠페인만 사용

### 5.3 Cosmos → Delta → Ranking

기존 `build_ranking()`을 그대로 사용해 검증했다.

검증 결과:

- 테스트 사용자 A: 100 points / 1위
- 테스트 사용자 B: 80 points / 2위
- Reward adjustment가 합계에 반영됨
- 부서 랭킹은 검증 fixture에 `department_id`가 없어 0행
- canonical Ranking Gold write는 하지 않음

### 5.4 기존 Cosmos `ranking` 컨테이너

확인 결과:

- 기존 컨테이너에는 과거 `score_kg_co2e` 기반 legacy ranking 문서가 존재
- 기존 legacy 문서는 덮어쓰지 않음
- 전용 테스트 캠페인에 `ranking-points-v1` 문서를 별도로 저장
- `score_unit = points`
- 100 / 80 points read-back 성공

### 5.5 Ranking API

기존 팀 공용 Function App `func-canopy-dev`에 `ranking_get`을 추가했다.

검증 결과:

```text
status = ready
week = 2026-W38
score_unit = points
personal_count = 2
department_count = 0

rank  points
1     100
2      80
```

따라서 현재 검증된 실제 경로는 다음과 같다.

```text
Actual Cosmos rewards
  → sandbox Reward Ledger Delta
  → build_ranking()
  → existing Cosmos ranking test document
  → Azure Function ranking_get
  → HTTP response
```

**주의:** 이 경로는 canonical Weekly Pipeline 전체 E2E와 동일하지 않다. canonical Reward Ledger Gold / Ranking Gold는 이 검증에서 쓰지 않았다.

---

## 6. 현재 코드상 중요한 미완료 구간

### 6.1 `baseline_gold()`

현재 코드:

```python
return empty_result(
    BASELINE_GOLD_SCHEMA,
    "personal_baseline",
    "global_baseline",
)
```

즉 Personal/Global 계산은 존재하지만 최종 Baseline Gold는 아직 실제로 조립되지 않는다.

### 6.2 `weekly_user_profile()`의 Mission History

현재 helper는 `mission_df`를 인자로 받지만 실제 계산에서 사용하지 않는다.

따라서 현재 상태는:

```text
Mission Response Delta 읽기 시도
→ build_weekly_user_profile(mission_df=...)
→ mission_df rows 실제 사용 안 함
```

미션 선호/난이도/완료 이력에 기반한 프로필 고도화는 아직 연결되지 않았다.

### 6.3 `next_week_missions()`

현재 코드:

```python
return empty_result(
    MISSION_BUNDLE_SCHEMA,
    "weekly_user_profile",
)
```

따라서 함수 선언과 schema는 있으나 실제 미션 생성은 아직 연결되지 않았다.

### 6.4 Reward Ledger → canonical Gold

Reward Ledger 자체는 실제 Cosmos와 sandbox에서 검증됐지만 `weekly_pipeline.py` 내부에 Reward Ledger materialization 단계가 없다.

현재 `ranking()`과 `campaign_kpi()`는 canonical 경로인:

```text
gold/reward_ledger_history
```

를 읽는다.

이 경로가 materialize되지 않으면 개발 fallback의 typed 0-row DataFrame을 사용하게 되어 Ranking이 0행이 될 수 있다.

### 6.5 `weekly_outputs_gold()`

현재 코드가 여전히 `empty_result(...)`이므로 앱 소비용 최종 통합 Gold가 실제 생성되지 않는다.

---

## 7. Campaign KPI 현재 해석

`campaign_kpi()` 계산 함수 자체는 연결돼 있다.

입력:

- Weekly Gold
- Campaign Membership
- Mission Response
- Behavior Change
- Reward Ledger

출력:

- enrolled user count
- active user count
- participation rate
- trip count
- distance / carbon
- mission assigned / completed
- mission completion rate
- behavior evaluable users
- changed users
- paid reward points

다만 현재 전체 KPI가 의미 있는 실데이터로 끝까지 검증됐다고 표현하면 안 된다.

이유:

1. Mission Response canonical 입력이 아직 확정/생성되지 않음
2. Reward Ledger canonical Gold가 아직 weekly canonical chain에 materialize되지 않음
3. Behavior Change는 충분한 다주차 이력이 없으면 `insufficient_data`
4. `weekly_outputs_gold`가 아직 placeholder

Behavior Change는 CANOPY 개입의 인과효과가 아니라 **관측된 전후 변화 KPI**로만 해석한다.

---

## 8. 현재 목표 대비 판정

### 목표 1 — 추가적인 Weekly 구조 대공사 없이 앱/E2E 연결

**부분 달성.**

주요 계산 helper와 Lakeflow 함수 구조는 이미 나뉘어 있어 남은 작업은 대부분 placeholder 교체와 upstream materialization 연결이다.

그러나 아래 세 곳은 실제 결과가 없기 때문에 아직 “구조 완성”이라고 할 수 없다.

- `baseline_gold`
- `next_week_missions`
- `weekly_outputs_gold`

### 목표 2 — Sandbox/iPhone 실데이터가 들어오면 끝까지 흐르기

**아직 미달성.**

Reward → Ledger → Ranking → API 구간은 별도 런타임 검증을 통과했다.

하지만 canonical weekly chain 기준으로는 Reward Ledger Gold materialization과 Mission/Baseline/Final Output 연결이 남아 있다.

### 목표 3 — 최신 정책과 팀원 코드 누락 없이 연결

**상당 부분 달성, 추가 점검 필요.**

현재 연결된 주요 기존 코드:

- Baseline policy / eligibility
- Personal / Global Baseline helper
- Behavior Change
- Ranking policy / build_ranking
- Campaign KPI
- Membership Delta 입력

남은 주요 연결:

- Mission Response 실제 소비
- Next Week Mission 실제 생성
- Reward Ledger canonical materialization
- 최종 Weekly Outputs contract

---

## 9. 다음 작업 우선순위

### P0 — Weekly Pipeline 전체 E2E를 막는 항목

1. `baseline_gold()` 실제 조립
2. Reward Ledger canonical Gold materialization 단계 연결
3. `next_week_missions()` 실제 계산 연결
4. `weekly_outputs_gold()` 실제 결과 생성
5. canonical 입력 상태에서 `ranking()` row 생성 확인
6. canonical 입력 상태에서 `campaign_kpi()` 실값 확인

### P1 — 운영 contract 정리

1. Mission Response weekly Delta 계약 확정
2. Reward Ledger Cosmos → Gold 실행 주체/순서 확정
3. Ranking Gold / Cosmos serving contract 하나로 통합
4. 부서 랭킹 실제 membership fixture로 검증
5. 앱 소비 API의 인증/캠페인/주차 정책 확정

### P2 — 최종 서비스 시연

1. 실제 iPhone / Expo Go 또는 개발 빌드에서 Ranking 화면 확인
2. 실제 Trip → Weekly → Reward → Ranking까지 데모 데이터로 회귀 테스트
3. 최종 발표용 E2E 증거 캡처

---

## 10. 작업 시 주의사항

- `empty_result(...)`가 남은 함수는 완료로 표시하지 않는다.
- Reward Ledger sandbox 성공을 canonical Gold 성공으로 표현하지 않는다.
- Ranking 테스트 문서를 운영 ranking 계약으로 확정하지 않는다.
- legacy carbon ranking과 points ranking을 혼합하지 않는다.
- Behavior Change를 인과효과로 표현하지 않는다.
- 사용자 수정 이동수단 값을 검증 없이 재학습 정답으로 사용하지 않는다.
- 새 Azure 상위 리소스를 임의로 생성하지 않는다.
- 기존 공용 `func-canopy-dev`, 기존 Cosmos, 기존 Databricks 리소스를 우선 재사용한다.

---

## 11. 현재 한 줄 요약

> **Weekly 계산 뼈대와 Baseline/Behavior/Ranking/Campaign KPI 주요 helper는 연결됐고 Reward Ledger→Ranking→API는 실제 런타임 검증까지 통과했다. 하지만 canonical Weekly E2E를 완성하려면 `baseline_gold`, Reward Ledger canonical materialization, `next_week_missions`, `weekly_outputs_gold` 연결이 아직 필요하다.**

# Mission v3.2 final handoff status — 2026-09-17

## 결론

Mission v3.2의 정책, schema, Profile, Assignment API, Progress 계산 코어, Response Weekly builder, Serverless Profile runner와 인수인계 계약을 최신 main 기준 하나의 브랜치/PR로 통합한다.

이 문서에서 `완료`는 **코드/계약/테스트 및 이미 수행한 Azure E2E 범위**를 뜻한다. `Mission Progress → Mission Response Weekly → Next Mission Profile`의 실제 Databricks/Lakeflow/ADF wiring은 통합 담당자의 작업이며 별도 완료 항목이다.

## 완료된 범위

- `mission-policy-v3.2` 정책 및 frozen assignment/completion rule 계약
- Weekly strict primary-mode fact: tie 및 invalid/null segment 제외
- Mission Profile v3 계산 및 ADLS history + Cosmos latest projection
- Databricks Serverless named Service Credential runner
- Function `GET /api/users/me/missions` cold/warm assignment
- same-week idempotency 및 Cosmos bundle 1건 유지
- warm bundle `profile_hash` == latest Profile `profile_hash`
- Mission Progress pure calculation core
- Mission Response Weekly pure builder
- Mission schema/data contract/handoff 문서
- Mission CI compile + policy/service/profile/serverless/progress/response tests

## 실환경 PASS 증거

기존 E2E 검증에서 확인된 핵심 결과:

```text
Weekly User Gold
→ Serverless Mission Profile
→ ADLS mission_profile
→ Cosmos latest profile
→ Function warm/cold Mission Bundle
```

Cold:
- starter 4 assignments
- repeated GET idempotent=true
- bundle_id/assignment_id 동일
- Cosmos mission_bundle 1건

Warm:
- profile_status_at_issue=current
- challenge_car_to_transit
- habit_transit_repeat
- easy_short_active
- explore_active
- bundle profile_hash == latest profile_hash

상세 증거는 `docs/azure/mission-v3-validation-result-20260916.md`를 본다.

## Progress / Response 완료 의미

Progress는 issued Bundle의 `completion_rule` snapshot + canonical ready Trip을 사용해 assignment별 current state를 idempotent recompute한다.

Response는 issued assignment마다 1행을 남기고 final Progress를 결합해 `mission_response_weekly` 분석 이력을 만든다. 미완료 assignment도 삭제하지 않는다.

```text
issued Mission Bundle + Final Trip
→ Mission Progress

Mission Bundle + final Mission Progress (+ optional UI events)
→ Mission Response Weekly
```

## 통합 담당자가 해야 할 wiring

```text
Final Trip Gold
  ├─→ Weekly User Gold
  │      └─→ Mission Profile(W+1) ← mission_response_weekly history
  │
  └─→ Mission Progress ← issued Mission Bundle
             ↓
      Mission Response Weekly
             ↓
      Next Mission Profile
```

필수 원칙:
- Progress 계산은 current policy를 재해석하지 않고 issued `completion_rule`만 사용
- Response는 4 assignments를 모두 보존
- 주간 history는 ADLS Gold `mission_response_weekly` 우선
- Cosmos는 Mission current/frozen operational state와 latest serving projection
- Mission과 Behavior Change는 서로 입력으로 연결하지 않음

## Behavior Change 경계

Behavior Change v1은 `Weekly User Gold`의 `total_kg_co2e` history를 직접 읽는 독립 branch다. Baseline, Reward, Ranking, Mission Response는 Behavior Change v1의 입력이 아니다.

상세 topology는 `docs/architecture/weekly-gold-integration-topology-v1.md`를 본다.

## 최종 상태 표현

```text
Mission policy/schema/core code: COMPLETE
Mission Profile + Assignment API real Azure E2E: PASS
Mission Progress core tests: PASS
Mission Response builder tests: PASS
Databricks/Lakeflow/ADF Progress→Response→Next Profile wiring: INTEGRATION OWNER TASK
```

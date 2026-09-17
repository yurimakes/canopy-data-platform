# Weekly Gold integration topology v1

기준일: 2026-09-17

이 문서는 `Weekly User Gold` 이후 Baseline, Behavior Change, Mission, Reward/Ranking의 **실제 의존관계**를 고정한다. 통합 담당자는 계산 편의를 위해 서로 독립인 feature를 직렬로 연결하지 않는다.

## 1. Canonical topology

```text
Final Trip Gold
      ↓
Weekly User Gold
      ├─→ Baseline Eligibility → Personal Baseline → Global Baseline
      │
      ├─→ Behavior Change v1
      │      ├─ before = 이전 2주 Weekly Gold total_kg_co2e 평균
      │      ├─ after  = 이후 1주 Weekly Gold total_kg_co2e 평균
      │      └─→ Behavior Change Gold → Campaign KPI / Power BI
      │
      ├─→ Reward Calculation ← Personal Baseline + Global Baseline + mission_response_weekly
      │      ↓
      │   Reward Ledger → Ranking
      │
      └─→ Mission Profile (mission_response_weekly history도 함께 사용)
              ↓
          Cosmos latest profile
              ↓
          Function GET /api/users/me/missions
              ↓
          frozen Mission Bundle (Cosmos)
              ↓
          Mission Progress ← Final Trip Gold
              ↓
          Mission Response Weekly (ADLS Gold)
              ├─→ Next Mission Profile
              ├─→ Mission KPI
              └─→ Campaign KPI Mission section
```

## 2. Behavior Change v1의 실제 입력

현재 구현 `cloud/azure/pipelines/databricks/build_behavior_change.py`는 `weekly_gold`를 직접 읽고 다음 필드만 사용한다.

```text
user_id
campaign_id
week
total_kg_co2e → metric_value
```

현재 정책:

```text
policy_version = behavior-change-policy-v1
before_window = 2주
after_window = 1주
minimum_delta = 0.0
```

판정 의미:

```text
before_avg = 평균(이전 2주 total_kg_co2e)
after_avg  = 평균(비교 1주 total_kg_co2e)
change_kg  = before_avg - after_avg

충분한 관찰치 + change_kg > 0 → changed
충분한 관찰치 + change_kg <= 0 → no_change
그 외                          → insufficient_data
```

따라서 **Behavior Change v1에는 Personal Baseline, Global Baseline, Reward, Ranking이 필요하지 않다.**

## 3. 금지 연결

아래 dependency는 현재 v1 계약에 존재하지 않는다.

```text
Baseline -X→ Behavior Change
Reward -X→ Behavior Change
Ranking -X→ Behavior Change
Mission Response -X→ Behavior Change
Behavior Change -X→ Mission Profile
```

필요하면 Campaign KPI/Power BI 단계에서 서로 다른 Gold 결과를 **나란히 소비**할 수 있지만, 이것은 feature 간 선행 의존관계가 아니다.

## 4. Baseline / Reward / Ranking 관계

Baseline은 Behavior Change가 아니라 Reward 쪽에서 의미가 있다. 현재 `calculate_reward.py`의 실제 입력은 다음과 같다.

```text
Weekly User Gold(current performance)
+ Personal Baseline
+ Global Baseline
+ mission_response_weekly(주간 미션 완료 수 metadata)
+ Reward policy
→ Reward Calculation
→ Reward Ledger Gold
→ Ranking Snapshot Gold
```

Reward는 `Weekly User Gold`에서 현재 주의 `actual_g_co2e_per_km`를 계산하고, Personal/Global Baseline과 비교해 상태와 포인트를 산출한다. `mission_response_weekly`의 완료 수는 현재 reward 결과 metadata에도 포함된다. Ranking은 실제 Reward Ledger 결과 이후에 계산하는 별도 downstream 단계다.

즉 **Baseline → Reward → Ranking** 연결은 존재하지만, 이 branch는 Behavior Change와 독립이다.

## 5. Mission 관계

Mission도 Behavior Change와 독립이다.

```text
Weekly User Gold(W)
+ mission_response_weekly history
→ Mission Profile(W+1)
→ Mission Bundle
→ Mission Progress
→ Mission Response Weekly
→ Next Mission Profile
```

Mission Response의 소비자는 다음 Mission Profile, Mission KPI, Campaign KPI Mission section이다. Behavior Change 입력으로 연결하지 않는다.

## 6. Databricks/Lakeflow wiring 원칙

1. `Weekly User Gold`가 준비되면 입력이 충족된 독립 branch를 병렬 실행할 수 있다.
2. Baseline 내부에서는 `Eligibility → Personal → Global` 순서를 지킨다.
3. Behavior Change는 Weekly Gold history만 준비되면 Baseline 완료를 기다릴 이유가 없다.
4. Reward는 해당 주 Weekly Gold와 필요한 Personal/Global Baseline, Reward policy가 준비된 뒤 실행한다. 현재 구현은 `mission_response_weekly`도 주간 미션 완료 수 metadata 입력으로 읽는다.
5. Ranking은 Reward Ledger가 준비된 뒤 실행한다.
6. Mission Profile은 Weekly Gold와 Mission Response history가 준비되면 실행한다.
7. Mission Bundle은 주간 Databricks Job이 선발급하는 분석 산출물이 아니라 Function API가 Cosmos에 최초 발급하는 frozen operational source다.
8. Mission Progress는 issued Bundle + canonical Final Trip을 사용한다.
9. Campaign KPI는 Weekly/Baseline/Behavior Change/Mission/Reward/Ranking의 결과를 downstream에서 합쳐 볼 수 있지만, 이 합류를 upstream feature dependency로 해석하지 않는다.

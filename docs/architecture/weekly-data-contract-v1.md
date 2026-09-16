# Canopy 주간 데이터 의존성 및 스키마 계약 v1

작성일: 2026-09-16  
기계 판독 계약: `shared/schemas/canopy_weekly_data_contract_v1.yaml`

## 1. 이 문서의 목적

`Weekly Summary`, `Eligibility`, `Personal/Global Baseline`, `Mission Profile`, `Mission`, `Reward`, `Mission Response`, `Behavior Change`, `Ranking`을 업무 순서가 아니라 **실제 데이터 의존성**으로 고정한다.

핵심은 모든 작업을 한 줄로 연결하지 않는 것이다. `Weekly Summary`에서 Baseline branch와 Mission branch가 갈라지고, Mission 실행 이후에야 `Behavior Change`가 생성된다.

```text
ready Canonical Trip
        |
        v
Weekly User Gold (W)
        |
        +---------------- Baseline branch -------------------+
        |                                                     |
        |   Eligibility -> Personal(W+1) -> Global(W+1)      |
        |                              |                      |
        |                              +-> Frozen Baseline ----+--> Trip Reward(W+1)
        |
        +---------------- Mission branch ---------------------+
             Weekly Gold(W) + past mission_bundle
                            |
                            v
                    Mission Profile(W+1)
                            |
                            v
                    Mission Bundle(W+1)
                            |
                   ready Trip during W+1
                            |
                            v
                    Mission Progress
                            |
                            v
                    Mission Response
                      /             \
                     v               v
          next Mission Profile    Behavior Change
                                     |
                                     v
                                 Campaign KPI

Reward Ledger -> Ranking Snapshot
```

## 2. 가장 중요한 의존성 결론

### Weekly Profile은 Behavior Change를 기다리지 않는다

`Behavior Change -> Weekly Profile`은 잘못된 의존성이다. 미션을 부여하려면 먼저 Profile이 필요하고, Behavior Change는 그 미션이 실제로 수행된 뒤에 계산된다.

올바른 순서는 다음과 같다.

```text
Weekly Summary
  -> Mission Profile
  -> Mission Bundle
  -> Trip 기반 Mission Progress
  -> Mission Response
  -> Behavior Change
```

### Baseline과 Mission Profile은 Weekly Summary 이후 병렬이다

```text
Weekly Summary
  +-> Eligibility -> Personal -> Global
  +-> Mission Profile
```

Mission Profile은 Global Baseline이나 Behavior Change가 없어도 생성 가능하다. 신규 사용자는 Profile 자체가 없어도 API cold start로 카테고리별 starter mission을 받을 수 있다.

### Personal -> Global은 직렬이다

Global은 같은 평가 주차의 `ready Personal baseline`을 동일 가중 평균하므로 Personal 계산이 먼저 끝나야 한다.

## 3. 주차 의미를 반드시 분리한다

Snapshot형 데이터에는 **원천 주차와 적용 주차를 섞지 않는다.**

예: W38 이동 결과로 W39의 기준과 미션을 준비하는 경우

```text
Weekly Summary
week = W38

Mission Profile
source_week = W38
effective_week = W39

Personal Baseline
evaluation/effective_week = W39
source = W38 및 그 이전 완료 주

Global Baseline
evaluation/effective_week = W39

Mission Bundle
week = W39

W39 Trip Reward
uses frozen W39 baseline snapshot
```

이 원칙을 지키면 현재 주 Trip이 현재 주 Baseline에 먼저 들어가는 leakage를 막을 수 있다.

## 4. Weekly User Gold: 공통 행동 Fact Layer

Producer: `cloud/azure/pipelines/databricks/build_weekly_summary.py`

Grain:

```text
user_id + campaign_id + week
```

기존 Baseline용 필드에 더해 Mission Profile에서 다시 Canonical Trip을 스캔하지 않도록 아래 파생 사실을 한 번만 계산한다.

| 필드 | 의미 |
|---|---|
| `valid_primary_trip_count` | 대표 이동수단을 유일하게 정할 수 있는 Trip 수 |
| `ambiguous_primary_trip_count` | 거리합 최대 mode 동률 등으로 대표 mode를 정하지 않은 Trip 수 |
| `car_primary_trip_count` | 대표 mode=car인 Trip 수 |
| `transit_primary_trip_count` | 대표 mode=bus/rail인 Trip 수 |
| `low_carbon_trip_count` | 대표 mode=walk/bike/bus/rail인 Trip 수 |
| `short_car_trip_count` | 대표 mode=car이고 총거리 2km 이하인 Trip 수 |
| `car_primary_ratio` | car primary / valid primary |
| `short_car_share` | short car / car primary |

대표 이동수단 규칙은 각 Trip의 segment를 mode별 거리로 합친 뒤 **거리합이 유일하게 가장 큰 mode**를 사용한다. 동률이면 임의로 고르지 않는다.

이 변경은 기존 Weekly Summary 필드를 삭제하거나 의미를 바꾸지 않는 additive extension이다.

## 5. Baseline branch

### Eligibility

입력:
- Weekly User Gold 이력
- 사용자/캠페인 가입·참여 시각
- `baseline_eligibility.yaml`

현재 구현 계약은 `eligibility-v1`이며 Personal 7일/출퇴근 Trip 6개/유효 거리·탄소, Global ready Personal 사용자 6명 기준을 사용한다. 이 값들은 계산 코드에 중복 하드코딩하지 않고 정책 파일에서 읽는다.

### Personal Baseline

Producer: `build_personal_baseline.py`

Grain:

```text
user_id + campaign_id + evaluation week
```

공식:

```text
이전 완료 주까지 누적 gCO2e / 이전 완료 주까지 누적 km
```

평가 주 자체는 분자/분모에 넣지 않는다.

### Global Baseline

Producer: `build_global_baseline.py`

Grain:

```text
campaign_id + evaluation week
```

공식:

```text
sum(ready Personal baseline) / count(ready Personal users)
```

캠페인 총 탄소 / 총거리와는 다른 지표다.

## 6. Mission Profile branch

Producer: `build_mission_profile.py`  
Version: `mission-profile-v3`

입력:

```text
Weekly User Gold
+ past Cosmos mission_bundle history
```

Runtime에서 Canonical Trip을 다시 집계하지 않는다. 행동 사실은 Weekly Gold에서 재사용한다.

Grain:

```text
user_id + campaign_id + source_week_start
```

핵심 필드:

```text
source_week_start
source_week_end
effective_week_start
profile_status
car_ratio
short_car_trip_count
short_car_share
transit_primary_trip_count
low_carbon_trip_count
carbon_change_rate
category_preferences
difficulty_state
family_capability
profile_version
profile_hash
```

카테고리 성향은 완료된 `preference_comparable=true` 미션만 양의 증거로 누적한다. 미완료는 비선호인지, 어려움인지, 기회 부족인지 구분하기 어려워 감점하지 않는다.

## 7. Mission Bundle

Producer: `mission_engine.py`  
Policy: `mission-policy-v3`

Grain:

```text
1 bundle / user_id + campaign_id + week_start
```

MVP 카테고리:

```text
challenge
habit
easy_win
explore
```

각 카테고리는 별도 `assignment_id`를 가진다. 사용자가 하나를 선택하는 POST 단계는 없다.

동일 주 bundle은 발급 뒤 고정한다. profile/policy가 같은 주 중간에 바뀌어도 기존 bundle을 자동 교체하지 않는다.

## 8. Reward branch

### 기본 탄소 보상은 Mission과 분리한다

기본 탄소 보상은 다음 입력만 필요하다.

```text
ready Canonical Trip
+ evaluation-week Personal Baseline
+ evaluation-week Global Baseline
+ Personal이 준비되지 않은 경우 external Population Baseline
+ reward_policy
```

`Mission Response`나 `Behavior Change`는 기본 탄소 보상의 필수 선행 데이터가 아니다.

Mission 완료 보너스를 도입하려면 별도 `reward_type=mission_bonus`로 처리한다.

### Reward grain

`baseline-policy-v4`의 `reward_context.granularity=trip`에 맞춰 다음 grain을 사용한다.

```text
trip_id + reward_type
```

동일 주의 모든 Trip은 같은 Weekly Frozen Baseline snapshot을 사용한다.

### Cold start

Personal이 준비되지 않은 첫 주에는 Population Baseline을 사용한다. Population 실제 숫자와 출처는 외부에서 주입한다.

```text
CANOPY_POPULATION_BASELINE_G_CO2E_PER_KM
CANOPY_POPULATION_BASELINE_SOURCE_ID
```

코드에는 임의 숫자를 넣지 않는다. 외부 값이 없으면 계산 결과는 `not_eligible`로 남기되 지급하지 않는다.

### Reward Ledger identity

기본 Trip 보상의 idempotency identity:

```text
campaign_id + user_id + reward_type + source_id(trip_id)
```

정책 버전이 바뀌었다는 이유로 같은 Trip에 두 번째 기본 보상을 만들지 않는다. 정정이 필요하면 원 지급을 보존하고 adjustment record를 추가한다.

## 9. Reward PR #26에서 보존한 부분과 교정한 부분

2026-09-16 merge된 PR #26의 팀원 구현을 기준으로 호환 수정했다.

보존한 설계:
- Reward 계산은 Cosmos Baseline latest가 아니라 ADLS Gold Baseline history를 읽는다.
- Personal 개선 판정을 Global 유지 판정보다 먼저 수행한다.
- 실제 포인트 환산율이 팀 합의 전이므로 임의 숫자를 넣지 않는다.
- Cosmos `create_item`을 사용해 중복 지급을 원자적으로 막는다.
- 지급 결과를 ADLS Reward Ledger history에도 미러링한다.

교정한 계약과 이유:

| 기존 PR #26 | 교정 | 이유 |
|---|---|---|
| 사용자/주차당 보상 1건 | Trip당 기본 탄소 보상 | `baseline-policy-v4`가 reward grain을 Trip으로 확정 |
| Personal/Global 모두 없으면 `not_eligible` | Personal 미준비면 Population fallback | Baseline cold-start 계약과 일치 |
| `user+campaign+week` reward id | `campaign+user+reward_type+trip_id` | 같은 주 여러 Trip 각각 보상하면서 재시도 중복 방지 |
| 기본 reward 계산이 Mission Response도 읽음 | Mission dependency 제거 | Mission과 기본 탄소 보상은 데이터 의존성이 없음 |
| points=null이어도 상태만으로 payable 가능 | points 확정 전 `payable=false` | null 지급 Ledger 방지 |

팀원 코드의 구조 자체를 갈아엎은 것이 아니라, 서로 다른 WBS에서 이미 확정한 Baseline 계약과 Reward 구현 사이의 인터페이스를 맞춘 것이다.

## 10. Mission Response와 Behavior Change

Mission Response는 Mission Bundle/Progress/Event와 실제 Trip을 한 주 단위로 묶는다.

권장 필드:

```text
bundle_id
assignment_id
mission_template_id
category_id
difficulty_band
target_count
preference_comparable
progress_count
achievement_rate
mission_completed_count
```

Behavior Change는 그 다음 단계다.

```text
Mission Response
+ 개입 전 Weekly behavior
+ 개입 후 Weekly behavior
+ Personal context
+ behavior_change_policy
-> changed / no_change / insufficient_data
```

이는 인과효과가 아니라 관측된 변화로 해석한다.

## 11. 저장소 역할

### ADLS Gold

계산/분석의 canonical processing source다.

- Weekly Summary
- Personal/Global History
- Mission Profile History
- Reward Calculation
- Reward Ledger History
- Mission Response
- Behavior Change
- Campaign KPI

### Cosmos DB

운영 상태와 low-latency 조회, 원자적 Ledger에 사용한다.

- Baseline latest serving copy
- Mission Profile latest
- Mission Bundle
- Reward Ledger
- Ranking Snapshot

Reward/Behavior 같은 batch job이 Cosmos Baseline latest를 canonical 중간 입력으로 사용하지 않는다.

## 12. 현재 남은 E2E 확인

코드 계약이 맞아도 다음은 실제 Azure에서 별도로 증명해야 한다.

- Weekly Gold 새 primary/short-car 필드 Delta 저장 및 재실행
- Weekly Gold -> Mission Profile 실제 입력 연결
- Cosmos Mission container partition key와 Managed Identity 권한
- 신규 사용자 GET -> 4카테고리 bundle -> 동일주 재조회
- 실제 Trip -> Mission Progress/Completion
- Population 공식 값/출처 주입
- Trip Reward Calculation -> Cosmos Reward Ledger -> ADLS history
- Reward Cosmos container partition key가 현재 코드의 `user_id`와 일치하는지 확인
- Reward Ledger의 현재 key/secret 인증을 프로젝트의 Managed Identity 원칙과 통합할지 확인

이 E2E 증거 전에는 관련 WBS를 최종 완료로 올리지 않는다.

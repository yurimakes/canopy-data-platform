# Canopy 주간 데이터 의존성 및 스키마 계약 v1

작성일: 2026-09-16  
기계 판독 계약: `shared/schemas/canopy_weekly_data_contract_v1.yaml`

## 1. 목적

`Weekly Summary`, `Baseline`, `Mission`, `Reward`, `Ranking`의 실제 데이터 의존성을 고정한다. Behavior Change는 별도 팀원 작업 영역이며 이 문서에서는 **Mission과 Behavior Change 사이에 데이터 의존성이 없다는 경계만 정의**한다. Behavior Change의 계산식·정책·grain·스키마는 이 문서가 소유하지 않는다.

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
                            |
                            v
                 next Mission Profile history

Reward Ledger -> Ranking Snapshot

Behavior Change
  = separate teammate-owned weekly behavior branch
  = no Mission Profile/Bundle/Progress/Response dependency
```

## 2. Mission과 Behavior Change 경계

최신 팀 합의에 따라 아래 연결은 **사용하지 않는다.**

```text
Mission Response -> Behavior Change   X
Mission Completion -> Behavior Change X
Mission Assignment -> Behavior Change X
Behavior Change -> Mission Profile    X
```

Mission 영역은 Mission 자체의 수행과 다음 주 개인화에만 책임진다.

```text
Weekly Summary
  -> Mission Profile
  -> Mission Bundle
  -> Trip 기반 Mission Progress
  -> Mission Response
  -> 다음 주 Mission Profile의 성향/난이도 이력
```

Behavior Change는 별도 업무 영역에서 Weekly Summary 등 팀이 합의한 기준 데이터로 계산한다. **미션 수행 여부를 Behavior Change의 원인이나 판정 입력으로 해석하지 않는다.**

## 3. Weekly Summary와 Mission Profile

Weekly Summary는 주간 이동행동의 공통 Fact Layer다.

Grain:

```text
user_id + campaign_id + week
```

Mission Profile이 Canonical Trip을 다시 집계하지 않도록 아래 행동 사실을 Weekly Gold에서 제공한다.

| 필드 | 의미 |
|---|---|
| `valid_primary_trip_count` | 대표 이동수단을 유일하게 정할 수 있는 Trip 수 |
| `ambiguous_primary_trip_count` | 대표 mode를 정하지 않은 Trip 수 |
| `car_primary_trip_count` | 대표 mode=car인 Trip 수 |
| `transit_primary_trip_count` | 대표 mode=bus/rail인 Trip 수 |
| `low_carbon_trip_count` | 대표 mode=walk/bike/bus/rail인 Trip 수 |
| `short_car_trip_count` | 대표 mode=car이고 총거리 2km 이하인 Trip 수 |
| `car_primary_ratio` | car primary / valid primary |
| `short_car_share` | short car / car primary |

대표 이동수단은 Trip segment를 mode별 거리로 합친 뒤 거리합이 **유일하게 가장 큰 mode**를 사용한다. 동률이면 임의 선택하지 않는다.

Mission Profile 입력:

```text
Weekly User Gold
+ past mission_bundle / mission outcome history
```

명시적 비입력:

```text
Behavior Change
Global Baseline
Reward Ledger
```

Mission Profile의 `carbon_change_rate`가 필요하다면 이는 Weekly Summary의 주간 탄소값에서 직접 계산하는 **Mission용 행동 feature**이며, Behavior Change Dataset을 읽는다는 뜻이 아니다.

## 4. Mission Profile / Bundle / Progress / Response

### Mission Profile

Producer: `build_mission_profile.py`  
Version: `mission-profile-v3`

Grain:

```text
user_id + campaign_id + source_week_start
```

### Mission Bundle

Producer: `mission_engine.py`  
Policy: `mission-policy-v3`

Grain:

```text
1 bundle / user_id + campaign_id + week_start
```

MVP는 `challenge`, `habit`, `easy_win`, `explore` 카테고리별 assignment를 함께 부여한다. 사용자가 하나를 선택하는 POST 단계는 없다.

### Mission Progress

입력:

```text
current Mission Bundle
+ ready Canonical Trip
+ mission_policy
```

역할은 assignment별 진행률·완료 여부를 계산하는 것까지다. Behavior Change를 읽거나 생성하지 않는다.

### Mission Response

권장 grain:

```text
campaign_id + user_id + assignment_id + week
```

권장 필드:

```text
bundle_id
assignment_id
mission_template_id
category_id
difficulty_band
target_count
preference_comparable
mission_shown_count
mission_started_count
mission_completed_count
progress_count
achievement_rate
linked_trip_count
```

주요 consumer:

```text
다음 주 Mission Profile
Mission 자체 KPI
Campaign KPI의 mission section
```

명시적 비consumer:

```text
Behavior Change
```

카테고리 성향 학습 규칙은 그대로 유지한다.
- `completed=true` + `preference_comparable=true` -> 해당 카테고리 positive evidence +1
- 미완료 -> 감점 없음
- 비교불가 완료 -> 수행 이력은 보존하되 preference 학습에서 제외

## 5. Reward와 Mission 분리

기본 탄소 Reward도 Mission 결과와 독립적이다.

```text
ready Canonical Trip
+ Frozen Personal/Global/Population Baseline
+ reward_policy
-> Trip Reward
-> Reward Ledger
-> Ranking
```

향후 Mission 완료 보너스를 도입할 때만 별도 `reward_type=mission_bonus`로 연결한다.

## 6. 주차 규칙

예: W38 이동 결과로 W39 미션을 만드는 경우

```text
Weekly Summary: W38
Mission Profile: source=W38, effective=W39
Mission Bundle: W39
Mission Progress/Response: W39
Mission Response history -> W40 Profile 입력
```

현재 주 결과가 같은 주 Profile 발급에 역으로 들어가지 않도록 source/effective week를 분리한다.

## 7. 저장소 역할

### ADLS Gold
- Weekly Summary
- Personal/Global History
- Mission Profile History
- Mission Response History
- Reward Calculation / Ledger History

### Cosmos DB
- Mission Profile latest
- Mission Bundle / operational mission state
- Baseline latest serving copy
- Reward Ledger
- Ranking Snapshot

## 8. 변경 기록

### 2026-09-16 — Mission / Behavior Change 분리

팀 합의에 따라 기존 문서의 다음 연결을 제거했다.

```text
Mission Response -> Behavior Change
Mission Progress -> Behavior Change
```

이번 수정 범위는 **Mission 쪽 경계 수정만**이다. Behavior Change의 정책, 계산 코드, 스키마, 검산 기준은 담당 팀원 영역으로 남긴다.

## 9. Mission 쪽 남은 E2E 확인

- Weekly Gold primary/short-car field 실제 Delta 저장
- Weekly Gold -> Mission Profile 실행
- Cosmos Mission container partition key / Managed Identity 권한
- 신규 사용자 GET -> 4카테고리 bundle -> 동일 주 재조회
- 실제 Trip -> Mission Progress / Completion
- Mission Response -> 다음 주 Mission Profile preference/difficulty 재생성

이 증거 전에는 Mission 관련 WBS를 최종 완료로 단정하지 않는다.

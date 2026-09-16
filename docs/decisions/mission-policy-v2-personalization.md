# 주간 미션 개인화 정책 v3

작성일: 2026-09-16
정책 버전: `mission-policy-v3`
프로필 버전: `mission-profile-v3`

## 1. 팀 합의

사용자가 미션을 고르는 구조를 사용하지 않는다.
서버가 매주 카테고리별 미션을 함께 부여하고, 실제로 완료한 미션의 카테고리를 사용자 성향의 양의 증거로 누적한다.

```text
카테고리별 미션 부여
→ 사용자가 일상에서 실제 수행
→ Trip 기반 진행률/완료 판정
→ 완료한 카테고리에 성향 점수 누적
→ 다음 주 미션과 난이도 개인화
```

## 2. 개인화 신호를 세 축으로 분리

### 이동행동 적합도
실제 이동 데이터로 어떤 미션 내용이 현실적으로 가능한지 판단한다.

- 자동차 이동 수
- 단거리 자동차 이동 수
- 대중교통 이동 수
- 저탄소 이동 수
- 최근 탄소 변화

### 카테고리 성향
어떤 동기 방식의 미션을 실제로 수행하는지 본다.

- `challenge`: 도전형
- `habit`: 꾸준형
- `easy_win`: 가벼운 실천형
- `explore`: 새로운 시도형

### 난이도/수행수준
카테고리와 별개로 사용자가 현재 어느 정도 목표량을 소화하는지 본다.

이 셋을 섞지 않는다.
특히 `challenge`라는 이유만으로 객관적 목표량을 더 높이지 않는다.

## 3. 첫 주 Cold Start

개인 데이터가 없는 첫 주에는 각 카테고리에서 starter 미션 1개씩 총 4개를 함께 부여한다.

- 사용자 선택 단계 없음
- 기본 공통 목표는 1회
- 같은 `difficulty_band=standard`
- 여러 미션을 동시에 완료할 수 있음
- 완료한 카테고리만 성향의 양의 증거가 됨

`1회`는 통계적 임계값이 아니라 최소 측정 가능한 행동 단위다.

## 4. 성향 학습

미완료는 성향의 부정 신호로 사용하지 않는다.
미션을 하지 않은 원인이 비선호인지, 난이도인지, 기회 부족인지 구분할 수 없기 때문이다.

MVP는 positive-only Dirichlet 형태로 구현한다.

```text
category_mass = prior + 완료한 비교가능 미션 수
preference_share = category_mass / 전체 category_mass 합
```

모든 카테고리는 같은 prior `1.0`에서 시작한다.

예:

```text
1주차
도전형 완료 / 꾸준형 미완료 / 가벼운 실천형 미완료 / 새로운 시도형 완료

→ challenge +1
→ explore +1
→ habit/easy_win 감점 없음
```

## 5. 난이도 비교가능성

성향 추론을 위해 같은 주의 카테고리별 미션은 최대한 같은 난이도로 맞춘다.

사용자별 `common_target_count`를 계산하고, 네 카테고리 미션에 같은 목표량을 기본 적용한다.

```text
직전 주 비교가능 미션 전체 완료 → +1
일부 완료 → 유지
하나도 완료하지 못함 → -1
최소값 → 1
```

단, 행동 기회가 부족해 특정 미션만 목표를 낮춰야 하면:

```text
target_count < common_target_count
preference_comparable = false
```

이 미션은 완료 이력은 남기되 성향 학습에는 사용하지 않는다.

## 6. 주간 저장 구조

한 사용자·캠페인·주차마다 `mission_bundle` 하나를 만든다.

```text
mission_bundle
- bundle_id
- user_id
- campaign_id
- week_start / week_end
- common_target_count
- policy_version
- missions[]
```

각 `missions[]`에는:

```text
assignment_id
category_id
mission_template_id
mission_family
mission_name
difficulty_band
target_count
preference_comparable
progress_count
achievement_rate
completed
status
```

카테고리별 `assignment_id`는 다음 키로 결정적으로 만든다.

```text
campaign_id + user_id + week_start + category_id
```

## 7. API

```text
GET /api/users/me/missions?week=YYYY-MM-DD
```

- 해당 주 bundle이 없으면 서버가 생성
- 이미 있으면 같은 bundle 반환
- 사용자 선택 API 없음
- 기존 `POST /api/users/me/missions/select` 제거

같은 주에는 profile이나 정책이 바뀌어도 이미 발급한 bundle을 자동 교체하지 않는다.

## 8. Profile v3

주간 profile은 다음을 합친다.

### 이동행동
- `car_ratio`
- `short_car_trip_count`
- `short_car_share`
- `transit_primary_trip_count`
- `low_carbon_trip_count`
- `carbon_change_rate`

### 성향
카테고리별:
- `prior`
- `assigned_count`
- `comparable_assigned_count`
- `completed_count`
- `positive_evidence_count`
- `preference_share`

### 난이도
- `last_common_target_count`
- `last_comparable_mission_count`
- `last_completed_comparable_count`

### family 분석
별도로 `family_capability`를 유지해 각 행동 family의 수행 이력을 추적한다.

## 9. 미션 자체의 품질 관리

성향에 관계없이 지속적으로 수행되지 않는 미션은 미션 자체 문제일 수 있으므로 별도 건강도 지표를 본다.

템플릿별 주간 집계:
- 부여 사용자 수
- 비교가능 부여 수
- 완료 사용자 수
- 완료율
- 평균 진행률

비교는 **같은 카테고리 + 같은 난이도 band** 안에서 한다.

정책:
1. 표본이 부족하면 판단하지 않음
2. 반복적으로 성과가 낮은 템플릿은 `review_candidate`
3. 자동 삭제하지 않음
4. 문구·행동 적합 조건·완료 조건을 검토
5. 필요하면 새 템플릿으로 교체
6. 정책 버전을 올리고 과거 발급 기록은 보존

최소 표본 수, 연속 주차 수, 성과 차이 임계값은 아직 팀 합의 전이므로 임의 수치를 코드에 넣지 않는다.

## 10. 현재 자동 테스트

핵심 검증 항목:
- 신규 사용자에게 4개 카테고리 동시 부여
- 사용자 선택 단계 없음
- 첫 주 동일 목표량
- 카테고리별 assignment ID 고유
- 행동 데이터에 따른 template 변경
- 공통 난이도 증가/유지/감소
- 행동 기회 상한 적용
- 목표량이 달라진 미션은 성향 비교 제외
- 완료한 카테고리만 긍정 증거 증가
- 미완료는 감점하지 않음
- 여러 미션 동시 완료 시 모두 점수 증가
- retired 템플릿은 신규 발급에서 제외
- 동일 주 bundle 재조회 시 고정

## 11. 구현 상태

브랜치: `feat/weekly-mission-v1`
PR: #24

주요 구현 파일:

```text
cloud/azure/functions/func_canopy_dev/mission_policy.yaml
cloud/azure/functions/func_canopy_dev/mission_engine.py
cloud/azure/functions/func_canopy_dev/mission_assignment_api.py
cloud/azure/pipelines/databricks/build_mission_profile.py
```

아직 merge하지 않는다.
Azure 실환경 E2E가 끝나기 전까지 PR 상태로 유지한다.

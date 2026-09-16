# 주간 미션 v3 배포 계약

작성일: 2026-09-16
정책 버전: `mission-policy-v3`
프로필 버전: `mission-profile-v3`

## 실행 흐름

```text
canonical ready Trip
  → Databricks build_mission_profile.py
  → ADLS Gold mission_profile 이력
  → Cosmos mission-profiles 최신 스냅샷
  → mission_policy.yaml + mission_engine.py
  → Azure Functions mission_assignment_api.py
  → Cosmos mission-assignments의 mission_bundle
  → GET /api/users/me/missions?week=YYYY-MM-DD
```

클라이언트 GET은 lazy/idempotent 방식이다. 해당 주의 `mission_bundle`이 없으면 API가 최신 profile과 정책을 읽어 카테고리별 미션을 함께 생성하고 저장한다. 이미 존재하면 같은 bundle을 그대로 반환한다.

사용자가 미션을 고르는 단계는 없으며 `POST /api/users/me/missions/select`는 사용하지 않는다.

## 필요한 Azure 설정

Function App 설정:

- `CANOPY_COSMOS_ENDPOINT` 또는 기존 `COSMOS_ENDPOINT`
- `CANOPY_COSMOS_DATABASE` 또는 기존 `COSMOS_DATABASE` (기본값 `canopy-db`)
- `CANOPY_COSMOS_MISSION_PROFILE_CONTAINER` (기본값 `mission-profiles`)
- `CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER` (기본값 `mission-assignments`)
- `CANOPY_CAMPAIGN_ID`
- `CANOPY_CAMPAIGN_TIMEZONE` (현재 MVP 기본값 `Asia/Seoul`)
- 운영 환경에서는 `CANOPY_ALLOW_DEV_USER_HEADER=false`

Databricks 추가 설정:

- `CANOPY_CONFIRMED_TRIPS_PATH`
- `CANOPY_GOLD_MISSION_PROFILE_PATH`
- `CANOPY_GOLD_WEEKLY_USER_PATH`

## Cosmos 컨테이너

현재 계약에서는 다음 두 컨테이너를 사용한다.

1. `mission-profiles`
2. `mission-assignments`

두 컨테이너 모두 partition key는 `/pk`이며 다음 규칙을 사용한다.

```text
pk = campaign_id + ':' + user_id
```

최신 mission profile ID:

```text
mission-profile-latest:{campaign_id}:{user_id}
```

주간 mission bundle ID는 다음 값으로 결정적 UUIDv5를 만든다.

```text
campaign_id + user_id + week_start
```

bundle 안의 각 카테고리 assignment ID는 다음 키로 만든다.

```text
campaign_id + user_id + week_start + category_id
```

반복 또는 동시 요청이 들어와도 같은 사용자·캠페인·주차에는 하나의 bundle로 수렴하도록 `create_item`을 사용하고, 이미 존재하는 경우 기존 문서를 읽는다. 같은 주의 미션을 profile 재계산으로 자동 덮어쓰지 않는다.

## 인증

운영 API는 Azure Easy Auth의 `x-ms-client-principal` 헤더에서 인증 사용자를 읽는다.

`X-Canopy-User-Id` 직접 입력은 `CANOPY_ALLOW_DEV_USER_HEADER=true`일 때만 허용하며 로컬/통합 테스트 용도다.

Azure Functions 자체 auth level은 `FUNCTION`을 사용하고, 사용자별 소유권은 Easy Auth principal claim으로 판단한다.

## 주간 경계

캠페인 로컬 시간 기준으로 월요일 00:00 이상, 다음 월요일 00:00 미만을 한 주로 본다.

API의 `week=YYYY-MM-DD`는 해당 주의 월요일로 정규화하고, Databricks는 이 로컬 경계를 UTC로 변환한 뒤 canonical Trip을 필터링한다.

`Asia/Seoul` 예시:

```text
2026-09-07 00:00 KST → 2026-09-06 15:00 UTC
2026-09-14 00:00 KST → 2026-09-13 15:00 UTC
```

## 데이터가 전혀 없는 신규 사용자

신규 사용자는 mission profile 문서가 없어도 미션을 받을 수 있다.

API가 `cold_start`로 판단해 각 카테고리 starter 미션을 1개씩 총 4개 부여한다.

첫 주에는:

- `common_target_count=1`
- 모든 카테고리 동일 난이도 band
- 사용자 선택 단계 없음
- 여러 미션 동시 수행 가능

완전 신규 사용자의 profile 행을 억지로 0 값으로 만들 필요는 없다. 최초 bundle 발급 후 수행 결과가 쌓이면 다음 주 profile 생성에서 history가 반영된다.

## 대표 이동수단 규칙

현재 canonical Trip에는 영구적인 Trip-level primary mode가 없으므로 mission profile은 세그먼트별 `model_prediction`과 `distance_m`를 사용한다.

각 Trip에서 이동수단별 세그먼트 거리 합을 계산하고, 합이 유일하게 가장 큰 mode를 대표 이동수단으로 사용한다.

정확한 동률이나 유효하지 않은 거리값은 임의로 결정하지 않고 valid 분모에서 제외하며 `invalid_trip_reasons`에 사유를 남긴다.

향후 canonical Trip 계약에 primary mode가 추가되면 version을 올려 이 파생 규칙을 교체한다.

## 성향과 난이도 데이터 계약

성향은 사용자의 선택이 아니라 **실제 완료 결과**에서 계산한다.

- 완료 + `preference_comparable=true` → 해당 카테고리 positive evidence +1
- 미완료 → 감점 없음
- 난이도 불균형으로 `preference_comparable=false` → 성향 계산에서 제외

난이도는 사용자별 공통 목표량을 사용한다.

```text
이전 주 비교가능 미션 전체 완료 → +1
일부 완료 → 유지
모두 미완료 → -1
최소 1
```

특정 미션의 행동 기회가 적어 target이 공통 목표보다 낮아지면 성향 비교 대상에서 제외한다.

## 미션 템플릿 건강도

지속적으로 수행되지 않는 템플릿은 사용자 성향과 별도로 분석한다.

집계 항목:

- 부여 사용자 수
- 비교가능 부여 수
- 완료 사용자 수
- 완료율
- 평균 진행률

비교는 같은 카테고리와 같은 난이도 band 안에서 수행한다.

낮은 성과가 반복되면 `review_candidate`로 올려 문구, 행동 적합 조건, 완료 조건을 검토한다. 자동 삭제하지 않고 새 템플릿이 필요하면 policy version을 증가시키며 과거 bundle은 기존 버전을 유지한다.

최소 표본 수·연속 주차·교체 임계값은 팀 합의 전이므로 현재 코드에 임의 숫자를 넣지 않는다.

## WBS 완료 전 검증 게이트

코드 게이트:

- mission-policy-v3 테스트 통과
- mission-profile-v3 집계 테스트 통과
- Function App 및 미션 모듈 컴파일 통과
- 사용자 선택 API가 존재하지 않음
- 신규 사용자 GET에서 4카테고리 bundle 생성
- 동일 주 반복 GET이 동일 bundle 반환
- 완료된 비교가능 미션만 성향 점수에 반영

Azure 통합 게이트:

- Cosmos 두 컨테이너가 `/pk` partition key로 존재
- Function Managed Identity가 필요한 Cosmos 데이터 권한 보유
- Databricks job이 Gold profile과 Cosmos 최신 profile 저장
- 신규 사용자 GET으로 4개 미션 bundle 생성 확인
- 반복 GET으로 같은 `bundle_id` 반환 확인
- 실제 Trip 진행률/완료 판정이 bundle 각 mission에 연결
- 다음 주 profile에서 완료 카테고리 positive evidence 반영 확인
- iPhone 미션 화면이 같은 bundle을 조회

Azure 통합 게이트 PASS 증거가 없으면 WBS API/profile 작업을 최종 완료로 표시하지 않는다.

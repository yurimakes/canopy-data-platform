# 저탄소 대중교통 길찾기 MVP

TMAP 대중교통 경로 응답을 Canopy 공통 경로 모델로 변환하고, 이동 구간별 거리와 교통수단별 배출계수로 탄소량을 계산한 뒤 실용성 제약 안에서 가장 낮은 탄소 경로를 추천합니다.

## 추천 규칙

1. TMAP 후보 중 최단시간 경로를 찾습니다.
2. 최단시간 대비 `max_time_over_fastest_pct` 이내이고, 환승 횟수가 최단시간 경로보다 `max_extra_transfers` 이상 늘지 않는 후보만 남깁니다.
3. 그 후보 중 탄소량이 가장 작은 경로를 `recommended`로 선택합니다.
4. `fastest`, `lowest_carbon`, `recommended`를 따로 반환합니다.

숨겨진 가중치 점수 하나로 시간을 탄소량에 억지로 합치지 않고, 사용자가 이해하기 쉬운 제약조건 기반 정책을 사용합니다.

## 탄소 계산

각 segment에 대해 다음을 계산하고 합산합니다.

`segment_gCO2e = distance_km × factor_gCO2e_per_passenger_km`

배출계수의 출처, 단위, 버전, 산정 경계를 함께 보관합니다. `data/reference/carbon_factors.demo.json`은 엔드투엔드 기능 검증용이며 운영 승인값이 아닙니다. 운영에서는 팀이 검증·확정한 `carbon_factors`만 사용해야 합니다.

## API

`POST /api/routes/low-carbon`

```json
{
  "start": {"lon": 126.926493082645, "lat": 37.6134436427887},
  "end": {"lon": 127.126936754911, "lat": 37.5004198786564},
  "count": 10,
  "max_time_over_fastest_pct": 20,
  "max_extra_transfers": 1
}
```

환경 변수:

```text
TMAP_APP_KEY=...
CARBON_FACTOR_FILE=../../data/reference/carbon_factors.demo.json
ALLOW_UNAPPROVED_CARBON_FACTORS=true   # 데모/테스트에서만
```

실행 예시:

```bash
cd apps/api
pip install -r requirements.txt
uvicorn canopy_api.main:app --reload
```

## Fixture

- `data/fixtures/transit/tmap_public_transit_20260912_trimmed.json`: 실제 성공한 TMAP 응답에서 경로 계산에 필요한 필드만 보존한 고정 fixture
- `data/fixtures/transit/odsay_api_key_auth_failed.json`: ODsay 인증 실패를 재현하는 negative fixture

실시간 API 응답은 그 자체로 자동으로 fixture가 되는 것이 아니라, 테스트를 반복 가능하게 만들기 위해 특정 입력/출력을 의도적으로 저장·고정했을 때 fixture로 사용합니다. 따라서 계속 덮어쓰는 `latest.json`보다 날짜/사례명이 고정된 파일을 회귀 테스트에 사용합니다.

## 현재 한계와 다음 단계

- 현재 구현은 TMAP 대중교통 후보들을 비교합니다. 자동차·자전거·도보까지 포함하는 완전한 다중수단 저탄소 길찾기는 각 수단의 경로 API를 추가한 뒤 동일한 공통 스키마와 탄소 계산기에 연결합니다.
- ODsay는 Server key와 등록 IP 인증이 정상화된 뒤 두 번째 provider adapter로 연결합니다.
- 운영 배출계수는 아직 팀에서 출처·단위·버전을 확정해야 하므로, 승인되지 않은 demo factor는 기본적으로 코드에서 차단합니다.

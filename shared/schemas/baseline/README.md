# Canopy Baseline Data Contract v1

이 문서는 `shared/schemas/baseline/baseline_data_contract_v1.yaml`을 사람이 빠르게 읽기 위한 설명서입니다. **Git의 YAML 계약을 canonical source of truth**로 사용하고, Notion은 팀 공유용 요약/링크로 사용합니다.

## 전체 흐름

```text
Cosmos trips (status=ready, commute-only)
  -> ADLS curated/confirmed_trips
  -> Weekly User Gold
  -> Eligibility v1
  -> Personal Baseline History
  -> Global Baseline History
  -> Cosmos Personal/Global latest
  -> Baseline API / Reward / Behavior Change / Ranking
```

## 인터페이스 요약

| 단계 | Producer | 입력 | 출력/저장 | Grain / Key | 다음 Consumer |
|---|---|---|---|---|---|
| Trip Baseline Input | `sync_confirmed_trips.py` | Cosmos `trips`, `status=ready` | `curated/confirmed_trips/` | latest `user_id + trip_id` | Weekly Gold |
| Weekly User Gold | `build_weekly_summary.py` | finalized commute Trips | `gold/weekly_summary_user/` | `user_id + campaign_id + week` | Eligibility / Personal |
| Eligibility | `baseline_eligibility.py` | Weekly history + membership/user joined time + YAML | status/metadata embedded into Personal/Global output | policy `eligibility-v1` | Personal / Global |
| Personal Baseline | `build_personal_baseline.py` | prior completed Weekly Gold | `gold/personal_baseline_history/` | `user_id + campaign_id + week` | Global / Cosmos / Reward |
| Global Baseline | `build_global_baseline.py` | same-week Personal snapshots | `gold/global_baseline_history/` | `campaign_id + week` | Cosmos / Reward / Behavior Change |
| Cosmos latest | `publish_baseline_snapshots.py` | Personal/Global Gold | runtime-configured Cosmos containers | deterministic latest IDs | Baseline API / Reward |

## 중요한 의미 계약

- 이 파이프라인으로 들어오는 Trip은 이미 **출퇴근 Trip만** 대상으로 합니다. 따라서 Weekly Gold의 `trip_count`는 Eligibility의 `minimum_confirmed_commute_trips`에 사용할 수 있습니다.
- 운영 시 `CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED=true`를 명시합니다. 이 값은 데이터 의미를 확인했다는 안전장치이지 새로운 필터가 아닙니다.
- 사용자 이의제기는 Trip 결과를 자동으로 바꾸지 않습니다. Baseline은 `status=ready` 자동 처리 결과를 사용하고, 인정된 오류 보상은 별도 수동 adjustment/audit 흐름에서 처리합니다.
- Weekly Gold는 탄소를 재계산하지 않고 upstream의 canonical `carbon.kg_co2e` / segment `carbon_kg`를 합산합니다.
- Personal은 **현재 평가 주차를 제외한 이전 완료 주 누적값**으로 계산합니다.
- Personal이 Eligibility를 만족하지 않으면 `population_fallback`이며, Population 실제 값은 별도 Population source가 제공합니다.
- Global은 `ready` Personal 사용자들의 gCO2e/km를 사용자 동일가중 산술평균합니다.
- Global은 `eligibility-v1` 기준 ready 사용자가 6명 미만이면 `collecting` + null을 유지합니다.

## Eligibility 운영 경로

```text
Git:  shared/configs/baseline_eligibility.yaml
ADLS: abfss://curated@stcanopydev5dt.dfs.core.windows.net/config/baseline/eligibility-v1/baseline_eligibility.yaml
ENV:  CANOPY_BASELINE_ELIGIBILITY_PATH
```

현재 `eligibility-v1`:
- Personal: 관측 7일 이상, 확정 출퇴근 Trip 6개 이상, 양의 거리, 유효 탄소값
- Global: Personal `ready` 사용자 6명 이상

## 버전/호환성 규칙

다음 변경은 breaking change로 보고 계약 버전을 올립니다.
- required field 삭제/이름 변경
- 단위 변경 (`m` ↔ `km`, `kgCO2e` ↔ `gCO2e` 등)
- grain/key 변경
- `ready` / `collecting` 의미 변경
- Personal/Global 공식 변경

새 필드 추가처럼 기존 consumer가 무시할 수 있는 변경은 같은 버전에서 additive change로 처리할 수 있습니다.

## 주의: legacy confirmation schema

`shared/schemas/confirmed_trip.schema.json`은 이전 confirmation 중심 설계의 흔적이 남아 있습니다. **Baseline v1의 실제 upstream 계약은 이 파일이 아니라 `sync_confirmed_trips.py`가 생성하는 `status=ready` finalized Trip slice**입니다. `trip.schema.json`의 confirmation 관련 설명도 사용자 이의제기를 자동 반영하라는 의미로 사용하면 안 됩니다.

## 변경할 때

1. Producer 코드 수정
2. `baseline_data_contract_v1.yaml` 또는 새 버전 계약 수정
3. 회귀 테스트 수정/추가
4. Consumer 담당자에게 breaking 여부 전달
5. 실제 ADLS/Cosmos/API 통합 검증

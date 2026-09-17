# Mission Progress / Mission Response 구현 인수인계 v1

기준일: 2026-09-17  
기준 main: `46f359849fb26ed5cd20e89c85247599263bce63`  
기준 정책: `mission-policy-v3.2`  
기준 계약: `shared/schemas/mission/mission_data_contract_v1.yaml`

이 문서는 **Mission 계산 코드 블록을 실제 Databricks/Lakeflow/ADF 파이프라인에 연결할 팀원**을 위한 구현 계약이다. 이 문서는 Notebook, Python module, Lakeflow pipeline, Databricks Job 중 특정 실행 방식을 강제하지 않는다. 담당자는 아래 입출력 계약과 idempotency 규칙을 유지한 채 현재 주간 통합 파이프라인에 연결한다.

> Mission과 Behavior Change는 서로 독립이다. Mission Response를 Behavior Change 입력으로 연결하지 않고, Mission Profile에도 Behavior Change를 넣지 않는다.

## 1. Canonical 데이터 흐름

```text
Final canonical ready Trip
        +
issued Mission Bundle (Cosmos operational source)
        ↓
Mission Progress 계산
        ↓
Mission Progress current state
        ↓
주간 마감
        ↓
Mission Response Weekly
        ↓
ADLS Gold / mission_response_weekly
        ↓
Next Mission Profile
        ↓
ADLS Gold / mission_profile + Cosmos latest projection
        ↓
GET /api/users/me/missions?week=...
        ↓
다음 주 frozen Mission Bundle 발급/조회
```

Mission Response의 소비자는 다음 세 곳이다.

```text
mission_response_weekly → next Mission Profile
mission_response_weekly → Mission KPI
mission_response_weekly → Campaign KPI의 Mission section
```

다음 연결은 금지한다.

```text
mission_response_weekly -X→ Behavior Change
Behavior Change -X→ Mission Profile
```

## 2. 현재 canonical schema와 grain

| Dataset | Schema | Grain |
| --- | --- | --- |
| Weekly User Gold | `shared/schemas/baseline/weekly_user_gold.schema.json` | `campaign_id + user_id + ISO week` |
| Mission Profile | `shared/schemas/mission/mission_profile.schema.json` | `campaign_id + user_id + effective_week_start` |
| Mission Bundle | `shared/schemas/mission/mission_bundle.schema.json` | `campaign_id + user_id + week_start` |
| Mission Progress | `shared/schemas/mission/mission_progress.schema.json` | `campaign_id + user_id + assignment_id + week_start` |
| Mission Response Weekly | `shared/schemas/mission/mission_response_weekly.schema.json` | `campaign_id + user_id + assignment_id + week_start` |
| Final Trip | `shared/schemas/trip.schema.json` / integration Final Trip Delta | latest `campaign_id + user_id + trip_id` |

Mission v3.2에서는 사용자가 후보 중 하나를 선택하지 않는다. 한 bundle에 `challenge`, `habit`, `easy_win`, `explore` assignment가 각각 하나씩, 총 4개 발급된다.

## 3. 운영 저장소와 분석 저장소의 역할

### Cosmos DB: 운영 current state

현재 dev 검증 환경:

```text
Cosmos account : cosmos-canopy-dev
Database       : canopy-db
Container      : mission-state
Partition key  : /pk
pk             : {campaign_id}:{user_id}
```

현재 같은 물리 container에 logical type을 구분해 저장한다.

```text
mission_profile   → 최신 serving projection
mission_bundle    → 그 주 발급 원본/frozen assignment
mission_progress  → 현재 진행 상태
```

Mission Bundle은 API가 최초 발급한 운영 원본이므로 Progress 계산에서 읽을 수 있다. 다만 주간 분석 이력은 Cosmos bundle을 장기 source로 반복 조회하지 않고 `mission_response_weekly` Gold로 마감한다.

권장 Mission Progress document envelope:

```json
{
  "id": "mission-progress:{assignment_id}",
  "pk": "{campaign_id}:{user_id}",
  "type": "mission_progress",
  "campaign_id": "...",
  "user_id": "...",
  "bundle_id": "...",
  "assignment_id": "...",
  "week_start": "YYYY-MM-DD",
  "target_count": 2,
  "progress_count": 1,
  "achievement_rate": 0.5,
  "completed": false,
  "completed_at": null,
  "status": "active",
  "qualified_trip_ids": ["trip-..."],
  "progress_version": "mission-progress-v1",
  "updated_at": "..."
}
```

같은 assignment를 다시 계산할 때 새 Progress 문서를 append하지 않고 같은 deterministic key에 upsert한다.

### ADLS Gold: 재현 가능한 주간 분석 이력

현재 계약상 경로:

```text
Weekly User Gold
abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/

Mission Profile Gold
abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_profile/

Mission Response Weekly Gold
abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_response_weekly/
```

`mission_response_weekly` 권장 partition은 `campaign_id + week_start`이다. 재실행 시 중복 append하지 말고 `assignment_id` key MERGE 또는 해당 campaign/week partition의 결정적 재작성 중 하나를 사용한다.

## 4. Final Trip 입력 경계

최신 main의 주간 통합 scaffold는 아래 개발용 Final Trip Delta를 실제로 읽기 시작했다.

```text
cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py
FINAL_TRIP_PATH =
abfss://curated@stcanopydev5dt.dfs.core.windows.net/
pipeline_test/trip_finalization/iphone_final_trips
```

현재 이는 **개발/통합 입력 경로**다. 운영 최종 경로가 확정되면 integrator가 같은 schema를 유지하면서 경로만 교체한다.

Mission Progress의 Trip 기본 필터:

```text
campaign_id == bundle.campaign_id
user_id == bundle.user_id
status == ready
week_start <= ended_at(Asia/Seoul) < week_end
```

같은 `trip_id`가 여러 번 존재하면 `(campaign_id, user_id, trip_id)`별 최신 `updated_at` 1건만 사용한다. 늦은 수정이나 재처리가 들어오면 이전 값에 delta를 더하기보다 해당 assignment를 canonical Trip set으로 **idempotent recompute**하는 것을 기본 규칙으로 한다.

## 5. 발급 당시 completion_rule snapshot만 사용

Progress는 현재 `mission_policy.yaml`을 다시 읽어 이미 발급된 미션의 규칙을 재생성하면 안 된다.

사용해야 하는 원본:

```text
mission_bundle.missions[].completion_rule
```

발급 시 snapshot에는 다음이 고정된다.

```text
metric
target_count
dedupe_key = trip_id
time_window = assignment_week
source = canonical_ready_trip
accepted_primary_modes
min_trip_distance_km (optional)
max_trip_distance_km (optional)
date_field (optional)
```

정책 파일이 주중에 바뀌어도 이미 발급된 bundle의 완료 기준은 바뀌지 않는다.

## 6. Trip primary mode 계약

Mission Progress의 Trip 대표 이동수단 판정은 Weekly Summary/Mission Profile과 완전히 같아야 한다.

현재 v3.2 mode source:

```text
segment.model_prediction
```

모든 segment가 아래 조건을 만족해야 Trip primary-mode fact가 유효하다.

1. mode가 `walk | bike | car | bus | rail` 중 하나
2. `distance_m`가 null이 아니고 `> 0`
3. mode별 segment distance 합 계산
4. 거리 합이 유일하게 가장 큰 mode 하나만 `primary_mode`
5. 최대 합 동률이면 invalid
6. mode null/unsupported 또는 distance null/non-positive segment가 하나라도 있으면 Trip 전체 primary-mode fact invalid

```text
mode_distance[m] = Σ segment.distance_m where segment.model_prediction = m
primary_mode = unique argmax(mode_distance)
```

Spark에서 NULL을 반드시 명시적으로 guard한다.

```python
invalid_segment = (
    F.col("effective_mode").isNull()
    | ~F.col("effective_mode").isin(["walk", "bike", "car", "bus", "rail"])
    | F.col("distance_m").isNull()
    | (F.col("distance_m") <= 0)
)
```

이 NULL case는 실제 Serverless Mission E2E에서 재현된 버그였고 수정 후 검증됐다. 최신 `weekly_analysis/weekly_pipeline.py`에도 동일 guard가 반영되어 있다.

## 7. completion_rule metric 의미

현재 지원 metric은 정확히 세 가지다.

```text
qualifying_trip_count
distinct_day_count
distinct_mode_count
```

공통 처리 순서:

```text
canonical ready Trip
→ assignment week filter
→ latest trip_id dedupe
→ valid primary mode 판정
→ accepted_primary_modes 필터
→ min/max total Trip distance 필터
→ metric 집계
```

거리 경계는 포함(inclusive)으로 해석한다.

```text
min_trip_distance_km → trip_distance_km >= min
max_trip_distance_km → trip_distance_km <= max
```

### qualifying_trip_count

```text
progress_count = qualifying unique trip_id count
qualified_trip_ids = qualifying unique trip_id 전체
```

### distinct_day_count

현재 policy의 `date_field`는 `ended_at`이다.

```text
local_date = Asia/Seoul 기준 date(trip[date_field])
progress_count = distinct local_date count
qualified_trip_ids = 조건을 통과한 Trip ID 전체
```

같은 날 Trip이 여러 건이어도 progress는 1이다.

### distinct_mode_count

```text
progress_count = distinct primary_mode count
qualified_trip_ids = 조건을 통과한 Trip ID 전체
```

같은 mode Trip이 여러 건이어도 mode 1종으로 센다.

한 Trip은 서로 다른 assignment의 서로 다른 metric을 동시에 진척시킬 수 있다. 단, 동일 assignment 안에서는 같은 `trip_id`를 두 번 세지 않는다.

## 8. Progress 상태 계산

기본 완료 판정:

```text
completed = progress_count >= target_count
```

v1 handoff convention:

```text
achievement_rate = min(progress_count / target_count, 1.0)
```

`progress_count`는 실제 값을 보존한다. 예를 들어 목표 2회에 qualifying Trip 4건이면 `progress_count=4`, `achievement_rate=1.0`이다.

`linked_trip_count`는 Response에서 `len(qualified_trip_ids)`로 계산한다. 따라서 `distinct_day_count`/`distinct_mode_count`에서는 `linked_trip_count`와 `progress_count`가 다를 수 있다.

상태:

```text
completed=true                       → completed
completed=false and now < week_end   → active
completed=false and now >= week_end  → expired
```

`completed_at`은 final canonical Trip set을 시간순으로 보았을 때 target을 처음 충족하는 Trip 시각으로 계산하는 것을 권장한다. Trip 수정 후 더 이상 목표가 충족되지 않으면 최종 canonical truth는 `completed=false`, `completed_at=null`이다.

클라이언트의 완료 버튼이나 `mission_completed` UI event는 완료 truth가 아니다. 최종 완료 truth는 canonical Trip에서 재계산한 Mission Progress다.

## 9. Mission Response Weekly 생성 계약

**발급된 assignment마다 반드시 1행**을 만든다. 완료한 assignment만 기록하면 안 된다.

현재 정상 bundle은 assignment 4개이므로 정상적인 주간 Response도 기본적으로 사용자당 4행이다.

```text
mission_bundle assignment snapshot
LEFT JOIN final mission_progress
LEFT JOIN optional mission UI events
→ mission_response_weekly
```

Progress row가 없더라도 assignment row는 남긴다.

```text
progress_count = 0
achievement_rate = 0.0
completed = false
linked_trip_count = 0
```

필드 source:

| Mission Response field | Canonical source |
| --- | --- |
| `campaign_id`, `user_id`, `week_start`, `week_end`, `bundle_id` | Mission Bundle |
| `assignment_id` | Mission Bundle assignment |
| `mission_template_id`, `mission_family`, `category_id`, `difficulty_band` | Mission Bundle assignment snapshot |
| `common_target_count` | Bundle/assignment snapshot |
| `target_count` | Assignment snapshot |
| `affinity_comparable`, `difficulty_comparable`, `preference_comparable` | Assignment snapshot |
| `progress_count`, `achievement_rate`, `completed` | Final Mission Progress |
| `linked_trip_count` | Final Progress `qualified_trip_ids` count |
| `policy_version` | Mission Bundle snapshot |
| `mission_shown_count`, `mission_started_count` | optional UI event aggregation |
| `mission_completed_count` | `1 if completed else 0` 권장; UI event를 truth로 사용하지 않음 |
| `response_version` | response implementation version |

Mission v3.2 Response에는 **offer set, 사용자 선택, selected_mission_template_id가 필요하지 않다.** 사용자 선택 구조는 폐기됐다.

## 10. 다음 주 학습 의미

Affinity는 심리적 선호를 인과적으로 추정하지 않는다. 현재는 분석용 descriptive signal이다.

```text
completed=true AND affinity_comparable=true
→ 해당 category positive evidence +1
```

미완료는 negative evidence가 아니다.

```text
completed=false → affinity 감점 없음
```

Cold-start starter는:

```text
affinity_comparable=false
difficulty_comparable=false
```

이므로 첫 주 온보딩 결과는 affinity/difficulty 학습에서 제외한다.

Difficulty는 최신 difficulty-comparable assignment 결과로 다음 `common_target_count`를 결정한다.

```text
직전 비교가능 assignment 전부 완료 → +1
하나도 완료하지 못함              → -1
일부 완료                         → hold
범위                              → 1..5
```

## 11. Mission Profile 연결점

`cloud/azure/pipelines/databricks/build_mission_profile.py`에는 이미 `mission_response_weekly` reader와 adapter가 있다.

환경 변수:

```text
CANOPY_GOLD_MISSION_RESPONSE_PATH
```

기본 Gold 경로:

```text
abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/mission_response_weekly/
```

Profile runtime은 Response Gold를 우선 읽어 assignment rows를 bundle history 형태로 묶는다. Response Gold가 정상 존재하면 `mission_history_source=mission_response_gold`가 되어야 한다. Cosmos bundle history fallback은 개발/전환기 명시적 허용 경로일 뿐 production canonical history가 아니다.

Databricks Serverless에서 Cosmos latest projection을 쓸 때는 implicit `DefaultAzureCredential()`에 의존하지 말고 프로젝트에서 검증한 named Unity Catalog Service Credential runner 패턴을 사용한다. credential name은 코드에 하드코딩하지 않고 `CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME` 설정으로 주입한다.

## 12. 최신 weekly_analysis pipeline에서 integrator가 바꿔야 하는 seam

기준 main `46f3598`의 `cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py`는 Final Trip → Weekly Gold까지만 실제 연결되어 있고, 이후는 담당자 code slot이다.

현재 seam:

```text
weekly_gold
→ weekly_user_profile  # 현재 mission_response input이 없음
→ next_week_missions   # 현재 materialized Mission Bundle placeholder
```

Mission v3.2 기준으로는 다음처럼 연결해야 한다.

```text
final_trip_gold_input ───────────────→ weekly_gold
        │
        └─ + issued mission_bundle ─→ mission_progress
                                      │
mission_bundle ───────────────────────┼─→ mission_response_weekly
optional UI events ──────────────────┘

weekly_gold + mission_response_weekly(history)
→ weekly_user_profile / Mission Profile Gold
→ Cosmos latest Profile publisher

Mission Profile latest
→ Function GET /api/users/me/missions
→ frozen Mission Bundle

Behavior Change
→ weekly_gold / baseline 등 자기 계약으로 별도 분기
```

따라서 integrator가 해야 할 핵심 변경은 다음과 같다.

1. `mission_response_weekly` stage/table을 명시한다.
2. `weekly_user_profile()`이 `weekly_gold`만이 아니라 `mission_response_weekly` history를 읽게 한다.
3. `next_week_missions()`를 **canonical pre-issued Mission Bundle Gold**로 사용하지 않는다. 현재 canonical 발급 원본은 Function API의 Cosmos `mission_bundle`이다. 예정 미션 preview가 필요하다면 별도 이름/역할로 두고 운영 bundle과 구분한다.
4. Mission Profile과 Behavior Change 사이에 dependency를 만들지 않는다.
5. 함수 내부 계산 코드와 storage publisher를 분리한다. Lakeflow transform은 DataFrame 반환, Cosmos publisher는 바깥 task로 두는 현재 scaffold 원칙을 유지한다.

## 13. Integration acceptance fixture

최소 아래 case를 모두 통과해야 한다.

- 같은 `trip_id` 재입력 → 같은 assignment progress 불변
- 수정된 latest Trip → assignment 전체 recompute 결과가 결정적
- 하나의 Trip이 서로 다른 assignment 두 개 이상을 조건상 충족 → 각각 progress 가능
- primary mode exact tie → Mission Progress에서 제외
- segment `model_prediction=NULL` → invalid Trip으로 제외
- unsupported mode 또는 non-positive distance → invalid Trip으로 제외
- `min_trip_distance_km` 경계값 정확히 같음 → 포함
- `max_trip_distance_km` 경계값 정확히 같음 → 포함
- distinct day: 같은 날 qualifying Trip 여러 건 → progress +1
- distinct mode: 같은 mode qualifying Trip 여러 건 → progress +1
- policy 파일 변경 후 재실행 → 기존 bundle snapshot rule 그대로 사용
- 미완료 assignment → Response row가 사라지지 않고 `completed=false`
- cold-start 4개 assignment → Response에는 남지만 affinity/difficulty learning 제외
- 같은 week Response 재실행 → row 수와 값 불변
- Response Gold 생성 후 다음 Profile → `mission_history_source=mission_response_gold`

## 14. 이미 검증된 upstream 범위

2026-09-16~17 실환경 E2E에서 다음은 PASS 상태다.

```text
Weekly User Gold strict primary-mode facts
→ Mission Profile 생성
→ ADLS Profile Gold write
→ Cosmos latest Profile upsert
→ Function cold-start 4 starter assignments
→ same-week repeated GET idempotency
→ warm-start Profile 기반 4 assignments
→ Mission Bundle profile_hash == latest Mission Profile profile_hash
```

따라서 후속 구현에서 다시 설계할 부분은 **Mission Progress → Mission Response Weekly → Next Mission Profile feedback**이다. 이미 검증된 Mission Bundle 발급 방식을 offer/selection 방식으로 되돌리면 안 된다.

## 15. 참고 파일

```text
shared/schemas/mission/mission_data_contract_v1.yaml
shared/schemas/mission/mission_bundle.schema.json
shared/schemas/mission/mission_progress.schema.json
shared/schemas/mission/mission_response_weekly.schema.json
shared/schemas/mission/mission_profile.schema.json
shared/schemas/baseline/weekly_user_gold.schema.json

cloud/azure/functions/func_canopy_dev/mission_policy.yaml
cloud/azure/functions/func_canopy_dev/mission_engine.py
cloud/azure/functions/func_canopy_dev/mission_assignment_api.py

cloud/azure/pipelines/databricks/build_mission_profile.py
cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py

docs/azure/mission-v3-validation-result-20260916.md
docs/azure/mission-v3-validation-runbook.md
```

## 16. 인수인계 완료 조건

Pipeline integrator가 아래 질문에 이 문서와 schema만 보고 답할 수 있으면 된다.

- 어떤 Trip을 Mission Progress에 넣는가?
- 어떤 rule을 기준으로 완료를 판정하는가?
- 중복/수정 Trip을 어떻게 처리하는가?
- Progress와 Response의 grain은 무엇인가?
- Response의 각 필드는 어디에서 오는가?
- 다음 Mission Profile이 무엇을 읽는가?
- Cosmos와 ADLS 중 어느 것이 operational current state이고 어느 것이 analytical history인가?
- Behavior Change와 Mission을 어디서 분리해야 하는가?

이 계약을 바꾸는 변경은 pipeline wiring 수정이 아니라 Mission policy/data contract 변경으로 취급하고 별도 PR에서 version과 함께 검토한다.

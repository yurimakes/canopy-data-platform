# Mission v3.2 schema index

Mission canonical policy: `mission-policy-v3.2`

이 디렉터리는 Mission의 **데이터 계약**을 정의한다. Databricks/Lakeflow/ADF 연결 코드는 이 schema를 소비해야 하며, pipeline 편의를 위해 Mission 의미를 다시 정의하지 않는다.

## Canonical flow

```text
Weekly User Gold
→ Mission Profile
→ Mission Bundle
→ Mission Progress
→ Mission Response Weekly
→ Next Mission Profile
```

- Mission Profile과 Behavior Change는 서로 독립이다.
- Mission v3.2에서는 사용자가 미션을 선택하지 않는다.
- 한 Mission Bundle에는 카테고리별 assignment 4개가 함께 발급된다.
- 발급된 assignment의 `completion_rule`은 주간 동안 frozen snapshot이다.
- 다음 주 Mission 학습 이력의 canonical analytical source는 `mission_response_weekly`다.

## Files

| File | Role | Grain |
| --- | --- | --- |
| `mission_profile.schema.json` | 다음 주 배정용 사용자 Profile | `campaign_id + user_id + effective_week_start` |
| `mission_bundle.schema.json` | 발급된 주간 bundle / 4 assignments | `campaign_id + user_id + week_start` |
| `mission_progress.schema.json` | assignment별 current progress | `campaign_id + user_id + assignment_id + week_start` |
| `mission_response_weekly.schema.json` | 주간 immutable Mission history | `campaign_id + user_id + assignment_id + week_start` |
| `mission_data_contract_v1.yaml` | dataset 관계, storage role, comparability contract | contract |

## Storage roles

```text
Cosmos DB
- latest Mission Profile serving projection
- current/frozen Mission Bundle
- current Mission Progress

ADLS Gold
- Weekly User behavior facts
- Mission Profile analytical history
- Mission Response Weekly immutable history
```

Cosmos를 주간 학습 history로 반복 조회하지 않는다. `mission_response_weekly`가 준비된 뒤 Next Mission Profile은 Gold history를 우선 사용한다.

## Integration handoff

상세 구현/배선 계약:

`docs/architecture/mission-progress-response-handoff-v1.md`

특히 다음을 확인한다.

- canonical ready Trip + latest `trip_id` dedupe
- Weekly Summary와 동일한 strict primary-mode contract
- issued `completion_rule` snapshot 사용
- `qualifying_trip_count`, `distinct_day_count`, `distinct_mode_count`
- incomplete assignment도 Mission Response row 유지
- cold-start assignment는 affinity/difficulty learning에서 제외
- Behavior Change dependency 금지

Pipeline integration이 이 계약을 변경해야 한다면 schema/data contract version 변경으로 별도 검토한다.

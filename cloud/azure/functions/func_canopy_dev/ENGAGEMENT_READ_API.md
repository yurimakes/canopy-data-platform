# 보상·랭킹 조회 API 인계

이 API는 조회 전용이다. 보상과 순위를 계산하거나 Databricks Job을 실행하지 않는다.

## 경로

- `GET /api/users/me/rewards?week=YYYY-MM-DD&page_size=50&cursor=...`
- `GET /api/rankings?week=YYYY-MM-DD&scope=individual&page_size=50&cursor=...`
- `GET /api/rankings?week=YYYY-MM-DD&scope=department&page_size=50&cursor=...`

사용자는 Easy Auth의 `x-ms-client-principal`에서 식별한다. `x-canopy-user-id`는
`CANOPY_ALLOW_DEV_USER_HEADER=true`인 로컬 개발에서만 허용한다. 요청에서 임의의
`user_id`나 `campaign_id`를 받지 않는다.

## 저장 projection

- Reward Ledger 컨테이너: 기존 `rewards`, partition key `user_id`
- Ranking Snapshot 컨테이너: 기본 `ranking-snapshots`, partition key `pk`
- Ranking `pk`: `{campaign_id}:{week_start}`
- Ranking Snapshot은 `campaign_id`, `week_start`, `week_end`, `scope`,
  `snapshot_status`, `generated_at`, `policy_version`, `aggregation_version`, `entries`를 가진다.
- 개인 entry의 내부 `user_id`, 부서 entry의 `member_user_ids`는 `is_me` 계산에만 쓰며
  API 응답에는 포함하지 않는다.

컨테이너 생성은 이 변경 범위가 아니다. Ranking Gold를 Cosmos 최신 조회값으로
반영하는 publisher가 위 projection을 기록해야 한다. 같은 주차에는 `generated_at`이
최신인 Snapshot만 조회한다.

## 환경 변수

- `CANOPY_COSMOS_ENDPOINT` 또는 `COSMOS_ENDPOINT`
- `CANOPY_COSMOS_DATABASE` (기본 `canopy-db`)
- `CANOPY_COSMOS_REWARD_LEDGER_CONTAINER` (기본 `rewards`)
- `CANOPY_COSMOS_RANKING_SNAPSHOT_CONTAINER` (기본 `ranking-snapshots`)
- `CANOPY_CAMPAIGN_ID` 또는 `TRIP_CAMPAIGN_ID`
- `CANOPY_CAMPAIGN_TIMEZONE` (기본 `Asia/Seoul`)

## 상태 구분

- 보상: `processing`, `settled`, `empty`
- 랭킹 Snapshot 없음: HTTP 200 + `snapshot_status=in_progress`, 빈 entries
- 잘못된 주차/scope/page/cursor: HTTP 400
- 미인증: HTTP 401
- Cosmos/서비스 장애: HTTP 503

응답 JSON Schema는 `shared/schemas/engagement/`에 있다.

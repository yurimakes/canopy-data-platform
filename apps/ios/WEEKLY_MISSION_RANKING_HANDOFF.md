# 주간 미션·랭킹 앱 화면 인계

## 적용 기준

- 미션 정책: `mission-policy-v3.2`
- 사용자가 후보를 선택하지 않는다.
- 서버가 한 사용자·캠페인·주차에 카테고리별 4개 assignment를 함께 발급한다.
- 동일 주 재조회는 같은 `bundle_id`와 `assignment_id`를 반환한다.
- 앱은 진행률, 완료 여부, 포인트, 순위를 계산하지 않는다.
- 미션 완료와 보상 확정은 별도 상태로 표시한다.
- 랭킹은 주차와 생성 시각이 있는 Snapshot이며 실시간 순위로 표시하지 않는다.

## 파일

- `src/engagementApi.ts`: API 응답 계약, 검증, HTTP adapter
- `src/engagementRuntime.ts`: Expo 설정과 실제/Mock adapter 선택
- `src/engagementMock.ts`: 개발용 고정 fixture 및 오류·빈 상태 adapter
- `src/ui/MissionRankingScreen.tsx`: 미션, 보상, 개인·부서 랭킹 화면
- `tests/engagement.test.ts`: 4개 자동 배정, 중복 ID, 보상/랭킹 검증, API 경로와 부분 실패 격리 테스트

## 서버 연결 계약

| 기능 | 요청 | 앱에서 필요한 핵심 필드 |
|---|---|---|
| 미션 | `GET /api/users/me/missions?week=YYYY-MM-DD` | `bundle_id`, 주차, 정책 버전, `missions[]` 진행률/상태 |
| 보상 | `GET /api/users/me/rewards?week=YYYY-MM-DD` | 처리 상태, 실제 지급/조정 points, 갱신 시각 |
| 개인 랭킹 | `GET /api/rankings?...&scope=individual` | 주차, Snapshot 상태/생성 시각, 개인 순위 |
| 부서 랭킹 | `GET /api/rankings?...&scope=department` | 주차, Snapshot 상태/생성 시각, 부서 순위 |
보상·랭킹의 점수는 계산 예정값이 아니라 지급/조정이 확정된 Ledger와 Ranking Snapshot을 API가 제공해야 한다. 앱은 Databricks나 Cosmos DB에 직접 접근하지 않는다.

미션은 조회 시 자동 배정되고 Final Trip과 서버에서 자동 매칭한다. 따라서 앱은 별도 선택·시작 API를 호출하지 않는다.

보상 또는 한쪽 랭킹 projection 조회가 일시적으로 실패해도 정상인 다른 섹션은 계속 표시한다.

Functions 구현과 Cosmos projection 계약은 `cloud/azure/functions/func_canopy_dev/ENGAGEMENT_READ_API.md`, 응답 schema는 `shared/schemas/engagement/`를 참고한다.

## 확인 명령

```bash
cd apps/ios
npm run typecheck
npx vitest run tests/engagement.test.ts
npx expo export --platform ios
```

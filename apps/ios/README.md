# Canopy iPhone GPS 수집 앱

React Native + Expo SDK 57 개발자용 수집 화면입니다. Trip 시작/종료, 수동 라벨 변경, SQLite 원본/전송 대기열, 재시도와 JSON 내보내기를 제공합니다. 서버 코드는 기존 `cloud/azure/functions/gps_ingest`와 HTTP로 연결하며 이 앱에 복제하지 않습니다.

## 실행

```powershell
cd apps/ios
npm ci
Copy-Item .env.example .env
# .env에 팀 GPS API 주소와 함수 키 설정
npm run start:tunnel
```

이미 `.env`가 있으면 복사로 덮어쓰지 않습니다. QR을 iPhone에서 열고 라벨 선택 → 측정 시작 → 종료합니다. GPS는 측정 중 자동 전송되고 종료 후에도 미전송 데이터는 남습니다. Expo Go에서는 화면을 켜 두어야 합니다. 환경설정 변경 후 Metro 재시작/앱 재로드가 필요합니다.

`POST /api/gps`, `x-functions-key` 헤더로 원본 이벤트 한 건을 전송합니다. HTTP 202와 `status=accepted` 응답에서 접수 완료로 처리합니다. 응답에 ID가 있으면 일치 여부도 확인합니다. API 접수는 Capture/Raw 저장 완료 증거가 아닙니다. 새 API 주소로 바꿔도 이전 주소에 묶인 대기열을 임의로 다른 서버에 전송하지 않습니다.

## 공통 계약

[GPS JSON Schema](../../shared/schemas/gps.collector.schema.json)를 사용합니다. 새 Trip은 `canopy.gps.collector.v0.2`, `collection_mode=developer`, `label=walk|bike|car|bus|rail`로 기록합니다. 라벨은 실제 측정 시각 기준입니다. 사용자용 화면은 추후 별도로 구현하며 `collection_mode=user`, `label=null` 계약입니다. label은 튜플이 아니며 undefined는 사용하지 않습니다.

기존 v0.1 원본·대기열을 수정하지 않고, 진행 중인 v0.1 Trip도 종료까지 기존 라벨을 유지합니다. 공통 스키마는 생산자 계약이며 Raw 수신 서버의 필드 선별/차단을 추가하지 않습니다. 기존 `gps_event_schema.xlsx`는 이전 계약 문서로 보존하며 v0.2의 추가 필드/라벨은 JSON Schema를 기준으로 검토합니다.

## 설치형 iOS 빌드

`app.json`에 위치 권한과 백그라운드 수집을 설정했고 `eas.json`의 preview는 내부 배포용입니다. EAS CLI로 `eas login`, `eas init`을 수행하고 실제 projectId를 app.json의 extra.eas.projectId에 기록합니다. preview 환경에 CANOPY_GPS_API_URL, CANOPY_GPS_FUNCTION_KEY를 설정한 뒤 Apple Developer 팀에서 기기를 `eas device:create`로 등록하고 `eas build -p ios --profile preview`로 빌드합니다. `.env`는 Git/EAS 업로드에서 제외됩니다. 공유 함수 키는 앱에서 추출 가능하므로 내부 테스트용 기존 인증 계약입니다.

설치형 앱은 잠금/앱 전환 중에도 위치 수집을 요청하지만 강제 종료 중 연속 수집은 보장하지 않습니다. 실제 Apple 서명 빌드 및 기기 검증은 별도입니다. 로컬 검사는 `npm run typecheck`, `npx expo export --platform ios`입니다.

## 주간 미션·보상·랭킹 화면

사용자용 이동 화면에서 `주간 미션` 또는 `랭킹`으로 들어갑니다. 서버가 카테고리별 미션 4개를 자동 배정하므로 사용자가 후보를 고르는 화면이나 선택 API는 없습니다. 앱은 서버가 반환한 미션 진행률·완료·포인트를 다시 계산하지 않습니다.

실제 연결 전에는 `.env`에서 `CANOPY_ENGAGEMENT_USE_MOCK=true`로 상태별 화면과 고정 fixture를 확인합니다. 실제 API 연결 시 false로 바꾸고 `CANOPY_ENGAGEMENT_API_URL`, 인증 토큰, Function Key를 설정합니다. 앱이 사용하는 계약은 다음과 같습니다.

```text
GET  /api/users/me/missions?week=YYYY-MM-DD
GET  /api/users/me/rewards?week=YYYY-MM-DD
GET  /api/rankings?week=YYYY-MM-DD&scope=individual|department
```

랭킹 화면은 `snapshot_status`, 주차, 생성 시각을 함께 표시하며 주간 Snapshot을 실시간 순위로 표현하지 않습니다. 미션은 조회 시 자동 배정되고 Final Trip과 서버에서 자동 매칭하므로 앱의 별도 선택·시작 요청은 없습니다. 보상·랭킹 Cosmos projection이 준비되기 전에는 Mock으로 검증합니다.

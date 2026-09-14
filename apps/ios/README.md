# Canopy iPhone GPS 수집 앱

React Native + Expo SDK 57 개발자용 수집 화면입니다. Trip 시작/종료, 수동 라벨 변경, SQLite 원본/전송 대기열, 재시도와 JSON 내보내기를 제공합니다. 서버 코드는 기존 `cloud/azure/functions/gps_ingest`와 HTTP로 연결하며 이 앱에 복제하지 않습니다.

## 실행

```powershell
cd apps/ios
npm ci
Copy-Item .env.example .env
# .env에 GPS 및 Trip API 설정 (아래 Trip API 연결 참고)
npm run start:tunnel
```

이미 `.env`가 있으면 복사로 덮어쓰지 않습니다. QR을 iPhone에서 열고 라벨 선택 → 측정 시작 → 종료합니다. GPS는 측정 중 자동 전송되고 종료 후에도 미전송 데이터는 남습니다. Expo Go에서는 화면을 켜 두어야 합니다. 환경설정 변경 후 Metro 재시작/앱 재로드가 필요합니다.

`POST /api/gps`, `x-functions-key` 헤더로 원본 이벤트 한 건을 전송합니다. HTTP 202와 `status=accepted` 응답에서 접수 완료로 처리합니다. 응답에 ID가 있으면 일치 여부도 확인합니다. API 접수는 Capture/Raw 저장 완료 증거가 아닙니다. 새 API 주소로 바꿔도 이전 주소에 묶인 대기열을 임의로 다른 서버에 전송하지 않습니다.

## Trip API 연결

`CANOPY_TRIP_API_URL=https://<Function App의 실제 호스트>/api`, `CANOPY_TRIP_ACCESS_TOKEN`에 해당 사용자의 유효한 access token, `CANOPY_TRIP_FUNCTION_KEY`에 Trip API용 함수 키 또는 공통 host key를 설정합니다. GPS 전용 함수 키는 Trip 함수에 사용할 수 없습니다. EAS 빌드에도 같은 설정이 필요합니다. 현재 앱에는 로그인 화면이 없으므로 환경변수의 access token은 개발 테스트용이며 만료되면 갱신해야 합니다. 로그인 기능을 붙일 때는 `backgroundLocationTask.ts`의 `tripConfig()`가 로그인 세션에서 최신 token을 가져오도록 연결합니다.

측정 시작은 `POST /api/trips/start` 응답을 받은 뒤 GPS를 수집합니다. 처음 시작할 때 인터넷이 필요하며 앱이 별도 Trip ID를 만들지 않습니다. 시작 응답이 유실되면 같은 요청 ID로 다시 시도합니다. 시작한 뒤에는 인터넷이 끊겨도 GPS를 로컬에 저장합니다.

측정 종료는 GPS 수집을 먼저 중단합니다. 해당 Trip의 GPS가 모두 접수되면 `POST /api/trips/{trip_id}/stop`을 보내고 `GET /api/trips/{trip_id}`를 조회합니다. `processing`, `ready`, `failed`와 segment 결과를 같은 화면에 표시합니다. 미전송 GPS와 종료 상태는 앱 재실행 후에도 남습니다. 앱이 강제 종료된 동안 재시도는 실행되지 않으며 다음 실행 시 이어집니다.

서버 설치, 로컬 테스트, Azure 배포는 [Trip API 실행 및 인계](../api/README.md)를 참고하세요. `npm test`는 PC의 Python 로컬 서버와 SQLite를 사용하며 Azure나 실제 iPhone에 접속하지 않습니다.

## 공통 계약

[GPS JSON Schema](../../shared/schemas/gps.collector.schema.json)를 사용합니다. 개발자용 새 Trip은 `canopy.gps.collector.v0.2`, `collection_mode=developer`, `label=walk|bike|car|bus|rail`로 기록합니다. 라벨은 실제 측정 시각 기준입니다. 첫 화면의 사용자용 버튼은 `collection_mode=user`, `label=null`로 수집하고, 개발자용 버튼은 라벨 선택 화면으로 진입합니다. 측정 중에는 화면 종류를 바꿀 수 없습니다. 버튼은 임시 화면 선택이며 계정 생성이나 인증 권한 부여를 하지 않습니다. 팀 로그인 연동 시 이 진입 선택을 인증 결과로 교체하면 됩니다. Trip API의 기존 토큰 설정은 여전히 필요합니다. label은 튜플이 아니며 undefined는 사용하지 않습니다.

기존 v0.1 원본·대기열을 수정하지 않고, 진행 중인 v0.1 Trip도 종료까지 기존 라벨을 유지합니다. 공통 스키마는 생산자 계약이며 Raw 수신 서버의 필드 선별/차단을 추가하지 않습니다. 기존 `gps_event_schema.xlsx`는 이전 계약 문서로 보존하며 v0.2의 추가 필드/라벨은 JSON Schema를 기준으로 검토합니다.

## 설치형 iOS 빌드

`app.json`에 위치 권한과 백그라운드 수집을 설정했고 `eas.json`의 preview는 내부 배포용입니다. EAS CLI로 `eas login`, `eas init`을 수행하고 실제 projectId를 app.json의 extra.eas.projectId에 기록합니다. preview 환경에 CANOPY_GPS_API_URL, CANOPY_GPS_FUNCTION_KEY를 설정한 뒤 Apple Developer 팀에서 기기를 `eas device:create`로 등록하고 `eas build -p ios --profile preview`로 빌드합니다. `.env`는 Git/EAS 업로드에서 제외됩니다. 공유 함수 키는 앱에서 추출 가능하므로 내부 테스트용 기존 인증 계약입니다.

설치형 앱은 잠금/앱 전환 중에도 위치 수집을 요청하지만 강제 종료 중 연속 수집은 보장하지 않습니다. 실제 Apple 서명 빌드 및 기기 검증은 별도입니다. 로컬 검사는 `npm run typecheck`, `npx expo export --platform ios`입니다.

# Trip API 실행 및 인계

04단계 Trip 시작, 종료, 상태 조회를 구현했습니다. 현재 처리기는 `MockTripProcessor`이며 실제 이동수단을 판별하지 않습니다. Azure 리소스 생성, 설정 변경, 배포는 수행하지 않았습니다.

## 연결 구조

앱 시작 버튼 → Trip API의 서버 생성 ID → 기존 GPS collector/SQLite/`POST /api/gps` → 앱 종료 버튼 → 미전송 GPS 접수 완료 → Trip 종료 API → DB의 `processing` 문서 → worker → processor → DB에 segments 저장 → `ready` 조회 순서입니다.

기존 `cloud/azure/functions/func_canopy_dev`의 GPS 수신과 4개 점검 함수는 수정하지 않았습니다. `tools/azure/package_trip_api.py`가 기존 앱에 Trip Blueprint를 등록한 배포 폴더를 만듭니다. Functions는 현재 팀 코드의 `DefaultAzureCredential`, `COSMOS_ENDPOINT`를 재사용하고 Trip DB는 `COSMOS_TRIPS_DATABASE`로 분리합니다. GPS payload, Event Hubs와 Capture 경로는 그대로입니다.

## API 계약

모든 Trip 요청에 `Authorization: Bearer <사용자 access token>`이 필요합니다. Azure Functions에서는 기존 `x-functions-key`도 필요합니다. 함수 키만으로는 사용자를 구분할 수 없어 Trip 소유자 검증을 대신하지 않습니다. 현재 저장소에는 사용자 로그인 구현이 없으므로 실제 issuer/audience와 앱 로그인 연결은 배포 전에 설정해야 합니다.

| Method / 경로 | 입력 | 성공 응답 |
| --- | --- | --- |
| POST `/api/trips/start` | `request_id`, `device_id` | 처음 201, 같은 요청 재전송 200. `trip_id`, `user_id`, `started_at`, `status=collecting` |
| POST `/api/trips/{trip_id}/stop` | `ended_at` 선택, `expected_last_sequence` 선택 | 202 `processing`; 이미 ready/failed면 현재 결과 200 |
| GET `/api/trips/{trip_id}` | 경로의 Trip ID | 200 현재 상태와 segments, model_version, failed_step, error_message |

`request_id`는 앱이 SQLite에 저장하는 시작 요청 번호입니다. 서버는 인증된 사용자와 이 번호로 UUID를 생성하므로 응답 유실/동시 재전송에도 Trip이 하나만 생깁니다. 같은 번호를 다른 `device_id`로 사용하면 409입니다. 사용자 ID는 검증된 token에서 얻으며 body로 다른 사용자를 지정하면 403입니다. 다른 사용자 Trip은 403 또는 파티션 조회 결과에 따라 404를 반환합니다. 미인증은 401, 잘못된 입력은 400입니다.

실패한 Trip을 재처리할 때만 stop body에 `{"retry":true,"retry_request_id":"새 요청 UUID"}`를 보냅니다. 같은 재시도 번호를 재전송해도 처리를 추가 실행하지 않습니다. ready Trip은 stop으로 다시 처리하거나 최초 모델 예측을 변경할 수 없습니다.

## Cosmos 저장 계약

팀에서 제공한 `cosmos_schema.json` 기준으로 database=`canopy-db`, container=`trips`, partition key=`/user_id`, `id=trip_id`입니다. 실제 컨테이너의 파티션키가 다르면 저장을 거부합니다. 컨테이너를 새로 만들거나 다른 파티션으로 옮기지 않습니다.

[공통 Trip 스키마](../../shared/schemas/trip.schema.json)에는 요청한 4개 상태와 결과 필드를 정의했습니다. 기존 스키마와 달라진 부분은 다음과 같습니다.

| 항목 | 처리 |
| --- | --- |
| status | 이번 요청의 collecting / processing / ready / failed 사용. 기존 ended / not_found 기록을 자동 변경하지 않음 |
| campaign_id | 서버 `TRIP_CAMPAIGN_ID` 설정값. 캠페인 가입 판정 기능은 구현 범위 밖 |
| segments | mode/start_time/end_time/confidence와 기존 model_prediction/started_at/ended_at/duration_min을 함께 저장 |
| 사용자 수정 필드 | confirmed_mode=null, corrected=false, correction_status=none 등 기존 필드 유지. 수정 API는 별도 작업 |
| 출발/도착/노선명 | 실제 처리기가 제공하지 않으면 null |
| carbon / planned_route | 계산·검색 미구현이므로 null. 값이나 경로를 지어내지 않음 |
| 운영 필드 | type=trip, created_at, updated_at, model_version, failed_step, error_message, is_mock 추가 |
| 내부 처리 필드 | start_request_id, fingerprint, processing_generation, expected_last_sequence, process_after, lease_until, worker_id, last_retry_id. API 응답에서는 내부 필드 제외 |

예시 저장 문서의 주요 부분입니다. 시간과 거리는 Mock 예시이며 실제 GPS 측정값이 아닙니다.

```json
{
  "id": "server-generated-trip-id",
  "trip_id": "server-generated-trip-id",
  "user_id": "authenticated-user",
  "campaign_id": "configured-campaign",
  "status": "ready",
  "started_at": "2026-09-14T07:00:00+00:00",
  "ended_at": "2026-09-14T07:01:00+00:00",
  "created_at": "2026-09-14T07:00:00+00:00",
  "updated_at": "2026-09-14T07:01:05+00:00",
  "segments": [{
    "segment_id": "server-generated-trip-id:segment:1",
    "mode": "walk", "model_prediction": "walk",
    "start_time": "2026-09-14T07:00:00+00:00",
    "end_time": "2026-09-14T07:01:00+00:00",
    "started_at": "2026-09-14T07:00:00+00:00",
    "ended_at": "2026-09-14T07:01:00+00:00",
    "distance_m": 72, "duration_min": 1, "confidence": 0,
    "confirmed_mode": null, "corrected": false, "correction_status": "none",
    "confirmation_time": null, "last_request_id": null,
    "start_name": null, "end_name": null, "route_name": null
  }],
  "model_version": "mock_v1", "is_mock": true,
  "failed_step": null, "error_message": null,
  "confirmation_status": "pending", "carbon": null, "planned_route": null
}
```

## Processor 교체 위치

[services/trip_processor.py](services/trip_processor.py)의 `TripProcessor.process_trip(trip)`가 인터페이스입니다. 입력은 trip_id, user_id, started_at, ended_at, expected_last_sequence, processing_generation을 포함한 Trip 문서입니다. 반환은 `{"trip_id":...,"model_version":...,"segments":[...]}`입니다. segment 필수값은 segment_id/mode/start_time/end_time/distance_m/confidence이며 mode는 walk/bike/car/bus/rail입니다.

현재 [services/mock_trip_processor.py](services/mock_trip_processor.py)는 5분 미만이면 walk 한 구간, 그 이상이면 walk/bus/walk를 생성합니다. confidence=0, model_version=mock_v1이며 화면에도 Mock이라고 표시합니다.

실제 코드가 준비되면 `services/real_trip_processor.py`에 같은 인터페이스의 클래스를 넣고 `TRIP_PROCESSOR=services.real_trip_processor:RealTripProcessor`로 바꿉니다. API route, 앱, Cosmos 저장 코드는 그대로 사용합니다. 처리기는 Raw/Curated 조회, 전처리, Azure ML, Transit Context 연결을 소유하며 DB 상태 저장은 `TripService`가 담당합니다. 실패 단계는 `ProcessingError('전처리 단계명', '내부 오류')`로 전달합니다. 클라이언트에는 민감한 내부 예외 문구를 보내지 않습니다.

앱은 GPS API 접수 완료 후 stop을 보냅니다. 이 시점에도 Event Hubs Capture 파일은 아직 없을 수 있습니다. 실제 처리기는 `expected_last_sequence`와 Raw의 event_id 중복 제거 결과를 대조해 입력이 모일 때까지 기다리거나 실패를 기록해야 합니다. Mock은 GPS를 읽지 않으므로 Raw 완전성을 증명하지 않습니다. 처리 완료 후 늦게 도착한 원본은 Raw에 보존되며 이 API가 자동으로 모델 결과를 덮어쓰지 않습니다.

stop은 상태와 대기 작업을 한 번의 Cosmos 조건부 갱신으로 저장합니다. Azure timer worker가 대기 문서를 읽고 ETag로 처리권을 얻습니다. 서버가 중단되면 15분 lease 만료 후 작업을 복구하며 이전 worker 결과는 ETag로 차단합니다. 따라서 정상 중복 요청은 한 번 처리하지만, 호스트 중단 시 processor 자체는 재호출될 수 있습니다. 실제 ML 호출은 `(trip_id, processing_generation)` 기준으로 멱등성을 구현해야 하며 실행 시간에 맞게 lease를 조정해야 합니다.

## 로컬 실행과 검증

Windows, Node 22.13 이상, Python 3.12/3.13을 사용합니다. 이 작업 폴더에는 의존성 설치를 마쳤습니다. 새로 clone한 경우만 다음을 실행합니다.

```powershell
cd apps/api
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cd ../ios
npm ci
cd ../..
```

저장소 루트에서 전체 로컬 검증을 실행합니다. Azure에 접속하지 않습니다.

```powershell
./tools/repo/check_trip.ps1
```

수동으로 로컬 API를 실행하려면 다음을 사용합니다. `--init`은 로컬 전용 token을 `.env`에 생성하며 기존 파일은 덮어쓰지 않습니다.

```powershell
cd apps/api
.venv/Scripts/python.exe local.py --init
.venv/Scripts/python.exe local.py
```

PC API 주소는 `http://127.0.0.1:8000/api`입니다. iPhone으로 로컬 서버에 접속하려면 같은 네트워크의 PC IP를 사용합니다. 앱 `.env`의 CANOPY_TRIP_API_URL을 그 주소로, CANOPY_TRIP_ACCESS_TOKEN을 API `.env`의 developer-test token으로, CANOPY_TRIP_ALLOW_LOCAL_HTTP=true로 설정합니다. HTTP 예외는 개발 빌드에서만 허용합니다. Expo 터널은 Metro 연결용이므로 별도의 로컬 Trip API까지 자동 공개하지 않습니다.

GPS API 설정은 기존 팀 주소와 키를 사용합니다. 실제 GPS 전송 없이 자동 테스트를 실행하는 `npm test`는 별도 합성 GPS 전송 함수를 사용합니다. GPS API가 설정되지 않으면 로컬 GPS가 대기하므로 종료 요청도 전송 대기 상태로 남습니다.

## Azure Functions 배포 순서

아래는 운영자가 수행할 절차입니다. 이 작업에서는 실행하지 않았습니다.

1. `5dt-2nd-team1` → `func-canopy-dev` → 설정 → 환경 변수에서 기존 Cosmos/Event Hubs/Key Vault/스토리지 설정을 유지합니다. 기존 COSMOS_DATABASE=canopy-smoke는 유지하고 COSMOS_TRIPS_DATABASE=canopy-db, COSMOS_TRIPS_CONTAINER=trips, APP_ENV=production, TRIP_STORE=cosmos, TRIP_PROCESSOR=mock, TRIP_CAMPAIGN_ID=실제 캠페인 ID를 추가합니다. COSMOS_DATABASE와 COSMOS_CONTAINER는 기존 점검 함수가 사용하므로 바꾸지 않습니다.
2. 같은 메뉴에 TRIP_AUTH_MODE=jwt, TRIP_JWT_ISSUER, TRIP_JWT_AUDIENCE, TRIP_JWKS_URL, TRIP_USER_ID_CLAIM을 팀 로그인 계약에 맞춰 넣습니다. JWT는 RS256 서명, 만료, issuer, audience를 검증합니다. 아직 로그인 제공자가 정해지지 않았다면 이 값은 임의로 채우지 않습니다. local 인증은 Azure에서 차단됩니다.
3. 같은 메뉴에 TRIP_WORKER_SCHEDULE=`*/30 * * * * *`, TRIP_PROCESS_DELAY_SECONDS=5, TRIP_PROCESS_LEASE_SECONDS=900을 추가합니다. 테스트가 끝나면 `AzureWebJobs.trip_worker.Disabled=true`로 timer를 멈출 수 있습니다. 다시 테스트할 때 false로 되돌립니다. Timer는 기존 AzureWebJobsStorage를 사용하며 주기적인 Cosmos 읽기가 발생합니다.
4. Cosmos 계정 → Data Explorer → canopy-db → trips → Settings에서 partition key가 `/user_id`인지 확인합니다. func-canopy-dev의 관리 ID에 이 DB/컨테이너의 Cosmos DB 데이터 읽기·쓰기 권한이 있어야 합니다. 일반 Azure IAM Reader/Contributor만으로 데이터 권한이 충족됐다고 판단하지 않습니다. 권한이 없으면 Cosmos 데이터 역할 할당 담당자에게 요청합니다.
5. 아래 패키지를 만든 뒤 현재 배포에 있는 함수와 저장소의 함수 목록을 비교합니다. 팀원이 새 함수를 추가했다면 먼저 그 소스를 반영합니다. 부분 앱을 공용 Function App에 배포하지 않습니다.

```powershell
# 저장소 루트: 로컬 파일 생성만 수행
apps/api/.venv/Scripts/python.exe tools/azure/package_trip_api.py

# 이후 명령은 실제 배포: 운영자가 실행
cd apps/api/build/func_canopy_dev
func azure functionapp publish func-canopy-dev --build remote
```

6. `func-canopy-dev` → 개요 → 함수에서 기존 health/gps_smoke/cosmos_smoke/keyvault_smoke/GpsIngest와 trip_start/trip_stop/trip_get/trip_worker를 확인합니다. 실제 함수 호스트 주소는 Portal의 기본 도메인을 사용합니다.
7. 각 Trip 함수의 함수 URL 가져오기 또는 앱 키에서 Trip 함수 키/host key를 확인해 앱 config에 설정합니다. 기존 GPS 전용 키를 다른 함수에 재사용하지 않습니다. 앱에 유효한 사용자 access token도 설정한 뒤 Metro를 재시작하거나 EAS를 다시 빌드합니다.
8. iPhone에서 측정 시작 → GPS 수집 → 종료 → ready 결과를 확인합니다. Cosmos Data Explorer에서 `/user_id`와 trip_id로 문서를 찾습니다. Application Insights에서 `trip_started`, `trip_processing`, `trip_result`, 해당 trip_id를 검색합니다. GPS가 Raw까지 갔는지는 기존 Capture 검증으로 별도 확인합니다.

공식 배포 및 연결 방식: [Python Functions Blueprint](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python), [Python 원격 빌드](https://learn.microsoft.com/en-us/azure/azure-functions/python-build-options), [Timer trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer).

## 검증 결과

2026-09-14 로컬 실행 기준입니다. 실제 Azure Cosmos 쓰기/조회와 실제 iPhone 시험은 수행하지 않았습니다.

| 요청 테스트 | 결과 |
| --- | --- |
| TEST 1 start → collecting | 통과. 로컬 SQLite 저장 확인 |
| TEST 2 중복 start | 통과. 동시 요청 8개에서 Trip 1개 |
| TEST 3 stop → processing → ready | 통과. 저장소 재연결 뒤 worker 실행 및 segments 보존 |
| TEST 4 GET 결과 | 통과. 같은 Trip ID와 Mock segments 반환 |
| TEST 5 중복 stop | 통과. 동시에 worker를 실행해도 정상 처리 1회 |
| TEST 6 강제 실패 | 통과. failed_step 저장, 명시적 재시도 및 중복 재시도 확인 |
| TEST 7 iPhone 전체 흐름 | 실제 iPhone은 배포 후 시험 필요. PC에서 앱 collector/SQLite와 실제 로컬 HTTP 서버를 연결한 대체 시험 통과 |

서버 테스트 14개, 앱 통합 테스트 7개, TypeScript 검사를 통과했습니다. Cosmos SDK 어댑터의 파티션·ETag 검사는 mock 컨테이너로 실행했습니다. DB가 실제 Azure에 저장됐다는 의미는 아닙니다.

## 파일과 인계 위치

| 분류 | 파일 | 역할 |
| --- | --- | --- |
| 신규 | apps/api/trip_routes.py | Trip HTTP 3개와 Azure timer Blueprint |
| 신규 | apps/api/services/trip_service.py | 시작/종료/조회, ETag 상태 변경, worker |
| 신규 | apps/api/services/cosmos_service.py | 기존 Cosmos 연결 및 로컬 SQLite 저장 |
| 신규 | apps/api/services/trip_processor.py | 실제 ML팀이 맞출 입력/출력 인터페이스 |
| 신규 | apps/api/services/mock_trip_processor.py | 합성 테스트 결과 생성 |
| 신규 | apps/api/services/runtime.py | 인증, 환경설정, processor 선택 |
| 신규 | apps/api/local.py, apps/api/.gitignore | 로컬 HTTP 서버와 로컬 데이터 제외 |
| 신규 | shared/schemas/trip.schema.json | 기존 Cosmos 필드와 Trip API 결과 계약 |
| 신규 | apps/ios/src/tripApi.ts | 영속 시작 요청, stop 재전송, GET polling |
| 신규 | apps/api/tests/test_trips.py, apps/ios/tests/trip.test.ts | 상태·장애·ID 일치 검증 |
| 신규 | tools/azure/package_trip_api.py, tools/repo/check_trip.ps1 | 공용 Functions 패키지, 로컬 검증 명령 |
| 수정 | apps/api/README.md, .env.example, requirements.txt | 인계/설정/의존성 |
| 수정 | apps/ios/src/collector.ts, location.ts | 서버 생성 trip_id로 측정 시작 |
| 수정 | apps/ios/src/storage.ts, types.ts | SQLite 시작 요청 보존 및 server 메타데이터 |
| 수정 | apps/ios/src/backgroundLocationTask.ts | Trip config 및 재시도 실행 |
| 수정 | apps/ios/App.tsx, src/ui/MeasurementScreen.tsx | stop 이후 상태 조회와 결과 표시 |
| 수정 | apps/ios/app.config.js, .env.example, README.md | Trip API 환경설정과 실행 방법 |
| 수정 | apps/ios/package.json, package-lock.json | 통합 테스트 명령과 개발 의존성 |

상태와 실행 결과는 이 문서에 모았습니다. GPS 원본, 실제 token, `.env`, node_modules, Python 가상환경, 생성된 배포 폴더는 커밋하지 않습니다.

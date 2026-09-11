# CANOPY GPS Ingestion E2E Verification — 2026-09-11

## 1. 목적

공용 Azure Function App에 배포된 `GpsIngest`의 HTTP validation과 Event Hubs 전달 경로를 synthetic GPS 이벤트로 검증한 결과를 기록한다. 실제 GPS 좌표, 사용자 식별자, 인증 정보는 이 문서에 포함하지 않는다.

## 2. 검증 환경

| 항목 | 확인값 | 상태 |
|---|---|---|
| Resource Group | `5dt-2nd-team1` | Confirmed |
| Function App | `func-canopy-dev` | Confirmed |
| Runtime / Hosting | Python 3.13 / Flex Consumption | Confirmed |
| Functions Storage | `stcanopyfunc5dt` | Confirmed |
| Data/ADLS Storage | `stcanopydev5dt` | Confirmed |
| Event Hubs Namespace | `evhns-canopy-dev` | Confirmed |
| Event Hub | `evh-canopy-gps-dev` | Confirmed |
| Function identity | SystemAssigned Managed Identity | Confirmed |
| Event Hub 권한 | Azure Event Hubs Data Sender | Confirmed |
| Identity connection prefix | `EVENTHUB` | Confirmed |
| Identity settings | `EVENTHUB__fullyQualifiedNamespace`, `EVENTHUB__credential=managedidentity` | Confirmed |

## 3. 배포 상태

- **Confirmed** — branch: `feature/gps-function-ingestion`
- **Confirmed** — deployed commit: `e3e9ea5`
- **Confirmed** — 실행 명령: `func azure functionapp publish func-canopy-dev --python`
- **Confirmed** — remote build 성공 및 deployment successful
- **Confirmed** — `GpsIngest` 등록, Host state `Running`
- **Confirmed** — route `POST /api/gps`, auth level `FUNCTION`

## 4. 로컬 검증

| 검증 | 결과 | 상태 |
|---|---|---|
| `python -m py_compile .\function_app.py` | 성공 | Confirmed |
| `python -m compileall .` | 성공 | Confirmed |
| `pytest -q` | 26 passed | Confirmed |
| Functions indexing | `GpsIngest` 및 `/api/gps` 확인 | Confirmed |
| `git diff --check` | 성공 | Confirmed |
| 배포 package | `function_app.py`, `host.json`, `requirements.txt`만 포함 | Confirmed |

배포 package에서 raw GPS, tests, reports, schemas, examples, scripts, `.venv`, `local.settings.json`이 제외된 것을 확인했다.

## 5. 정상 요청 E2E 결과

Synthetic GPS 이벤트를 사용했으며 `speed=null`을 포함했다. 구체적인 synthetic 식별자와 좌표는 기록하지 않는다.

| 확인 항목 | 결과 | 상태 |
|---|---|---|
| HTTP 응답 | 202 | E2E Verified |
| response 식별자 | 입력 `event_id`, `trip_id` 보존 | E2E Verified |
| Event Hub 수신 | 실제 메시지 수신 | E2E Verified |
| Event Hub 식별자 | 입력과 동일한 `event_id`, `trip_id` | E2E Verified |
| nullable speed | `speed=null` 보존 | E2E Verified |
| canonical field 수 | 10 | E2E Verified |

검증 흐름은 synthetic payload 생성 → Function key 인증을 사용한 HTTP POST → 응답 확인 → Event Hub consumer 수신 → 식별자·nullable 값·field 수 대조 순서로 수행했다. 인증값은 파일이나 문서에 저장하지 않았다.

## 6. Invalid Coordinate 결과

- **Confirmed** — synthetic `lat=91` 요청에 HTTP 400 반환
- **Confirmed** — response: `{"code":"out_of_range","field":"lat"}`
- **Check Needed** — 이 요청의 Event Hub 미전송 여부는 consumer 결과와 직접 대조하지 않았다.

## 7. Duplicate Event 결과

동일한 synthetic GPS 이벤트를 두 번 요청했다. 구체적인 식별자와 좌표는 기록하지 않는다.

- **E2E Verified** — 두 HTTP 요청 모두 202
- **E2E Verified** — Event Hub에서 동일 `event_id` 메시지 2건 수신
- **E2E Verified** — 두 payload 모두 동일 `trip_id`, `speed=null`, field count 10
- **Confirmed** — 관측 partition은 서로 달랐으며 partition ID는 1과 2였다.
- **Confirmed** — 현재 Function은 duplicate `event_id`를 reject하거나 deduplicate하지 않는다. 이는 현재 정책과 구현의 관측 결과이며 결함으로 단정하지 않는다.

## 8. 확인된 사실

- **E2E Verified** — HTTP Function → validation → Event Hubs 정상 전달 경로
- **Confirmed** — canonical 출력은 core field 10개로 제한됨
- **Confirmed** — `speed=null`이 HTTP 및 Event Hub 경로에서 보존됨
- **Confirmed** — 입력의 `event_id`, `trip_id`가 변환되지 않음
- **Confirmed** — 좌표 범위 validation이 적용됨
- **Confirmed** — duplicate 요청은 현재 그대로 통과함
- **Confirmed** — partition key가 고정되지 않은 상태에서 동일 event/trip이 서로 다른 partition에 배치된 사례가 관측됨

## 9. 확인되지 않은 사항

- **Check Needed** — invalid coordinate 요청이 Event Hub에 전달되지 않았는지 직접 대조
- **Check Needed** — Application Insights trace 경로. 성공 `event_id` 검색과 최근 traces 검색에서 결과가 없었으며 원인은 추정하지 않는다.
- **Check Needed** — 운영 부하, retry, 장애 복구 및 장시간 처리 특성

Application Insights trace 확인과 별개로, E2E 성공은 Event Hub에서 메시지를 직접 수신해 확인했다.

## 10. 남은 팀 결정

- **Team Decision Needed** — Event Hubs partition key 정책
- **Team Decision Needed** — trip ordering 보장 필요 여부
- **Team Decision Needed** — duplicate `event_id`의 idempotency/deduplication 정책
- **Team Decision Needed** — 최종 canonical `schema_version`

`trip_id`를 partition key로 사용하는 방안은 확정된 정책이 아니다.

## 11. 보안 정리

- **Confirmed** — 테스트 후 Event Hub SAS 환경변수 제거
- **Confirmed** — Function key PowerShell 변수 제거
- **Confirmed** — secret, Function key, SAS, Connection String을 파일이나 Git에 저장하지 않음
- **Confirmed** — 실제 GPS 좌표와 사용자 식별자를 문서에 기록하지 않음

## 12. 다음 작업

1. invalid coordinate 요청과 Event Hub consumer 결과를 같은 관측 구간에서 직접 대조한다.
2. Application Insights logging 및 trace 수집 경로를 확인한다.
3. partition key와 trip ordering 요구사항을 팀에서 결정한다.
4. duplicate 이벤트 처리 정책과 최종 canonical schema version을 결정한다.

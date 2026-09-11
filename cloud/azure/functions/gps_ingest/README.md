# GPS ingest Azure Function

## 목적

iPhone GPS 수집 이벤트를 검증하고 canonical GPS 이벤트의 핵심 필드만 Azure Event Hubs로 전달합니다.

현재 공용 Function App의 실제 runtime과 hosting은 Python 3.13 / Flex Consumption입니다. Python 3.13은 이 Function App의 현재 runtime이며 팀 전체 Python 표준을 의미하지 않습니다.

## 배포 주의

`func-canopy-dev`는 팀이 공유하는 공용 Function App이며, 이 디렉터리는 GPS ingestion 컴포넌트의 소유 위치입니다. 향후 공용 Function App에 다른 Function이 함께 존재하는 경우 이 `gps_ingest` 디렉터리만 기준으로 공용 Function App을 단독 재배포하지 않습니다.

공용 Function App을 배포하기 전에는 팀 저장소의 전체 Function 구성과 배포 패키지 범위를 확인해야 합니다. 이는 현재 팀 협업 안전을 위한 주의사항이며 새로운 Azure 정책이 확정되었음을 의미하지 않습니다.

## HTTP 경로

- Function: `GpsIngest`
- Route: `POST /api/gps`

## 이벤트 계약

Event Hubs로 전달하는 core GPS 10 fields는 다음과 같습니다.

- `event_id`
- `user_id`
- `trip_id`
- `event_time`
- `lat`
- `lon`
- `accuracy`
- `speed`
- `sequence`
- `schema_version`

`speed`는 required key이지만 값은 `null`일 수 있습니다. 누락되거나 `null`인 값을 임의로 `0`으로 처리하지 않습니다.

## Event Hubs 연결

Event Hubs 연결에는 System Assigned Managed Identity를 사용하며, Function identity에는 `Azure Event Hubs Data Sender` 권한이 필요합니다.

필요한 설정 이름은 다음과 같습니다.

- `EVENTHUB_NAME`
- `EVENTHUB__fullyQualifiedNamespace`
- `EVENTHUB__credential` (`managedidentity`)

## 팀 결정 필요

다음 정책은 아직 확정하지 않았습니다.

- 최종 canonical `schema_version`
- Event Hubs partition key
- trip ordering 보장 여부
- duplicate `event_id`의 idempotency/deduplication 정책

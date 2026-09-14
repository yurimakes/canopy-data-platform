# GPS ingest Azure Function

## 목적

iPhone GPS 수집 이벤트를 Medallion Architecture의 Bronze 원본 이벤트로 Azure Event Hubs에 전달합니다. 애플리케이션은 JSON payload의 필드나 값을 검사·정규화·선별하지 않으며, 수신한 JSON text를 그대로 output binding에 설정합니다.

현재 공용 Function App의 실제 runtime과 hosting은 Python 3.13 / Flex Consumption입니다. Python 3.13은 이 Function App의 현재 runtime이며 팀 전체 Python 표준을 의미하지 않습니다.

## 배포 주의

`func-canopy-dev`는 팀이 공유하는 공용 Function App이며, 이 디렉터리는 GPS ingestion 컴포넌트의 소유 위치입니다. 향후 공용 Function App에 다른 Function이 함께 존재하는 경우 이 `gps_ingest` 디렉터리만 기준으로 공용 Function App을 단독 재배포하지 않습니다.

공용 Function App을 배포하기 전에는 팀 저장소의 전체 Function 구성과 배포 패키지 범위를 확인해야 합니다. 이는 현재 팀 협업 안전을 위한 주의사항이며 새로운 Azure 정책이 확정되었음을 의미하지 않습니다.

## HTTP 경로

- Function: `GpsIngest`
- Route: `POST /api/gps`

## Bronze 수집 계약

JSON으로 해석 가능한 HTTP body는 필수 필드, 타입, 위·경도 범위, `speed`, `sequence` 등의 내용 검사를 하지 않습니다. CANOPY core fields는 별도로 식별·추출하지만, 추출 결과를 validation이나 Event Hubs 전송 필터로 사용하지 않습니다. Bronze에는 추가 필드와 아직 정의되지 않은 필드를 포함한 원본 JSON payload 전체를 보존하여 전달합니다.

CANOPY core fields는 다음과 같습니다.

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

`speed`는 CANOPY core field 중 하나이며 값은 `null`일 수 있습니다. 클라이언트가 제공한 `speed=null`과 `event_time`은 변경하지 않고 그대로 보존합니다. 누락된 core field도 요청 거절 사유가 아니며 추출 결과에서는 `None`으로 나타납니다.

성공 응답은 HTTP 202와 `{"status":"accepted"}`입니다. 응답은 `event_id`나 `trip_id`가 있다는 전제를 두지 않습니다.

현재의 최소 HTTP 경계 처리는 body가 JSON으로 해석되지 않으면 HTTP 400 `{"code":"invalid_json"}`을 반환하고 Event Hubs output을 설정하지 않는 것입니다. JSON 객체뿐 아니라 배열·스칼라처럼 파싱 가능한 JSON은 내용에 따라 거절하지 않습니다. JSON으로 해석 불가능한 raw body까지 별도 형식으로 Bronze에 저장할지는 팀에서 아직 결정하지 않았으며, 현재 구현은 그 범위까지 보존하지 않습니다.

## Timestamp

애플리케이션은 ingestion timestamp를 payload에 추가하지 않습니다. 따라서 클라이언트의 기존 `event_time`을 변경하거나 삭제하지 않으며, 애플리케이션이 만든 timestamp가 payload에 중복으로 생기지 않습니다.

수신 시각은 Event Hubs가 이벤트를 수락할 때 부여하는 UTC enqueue timestamp(system property)를 기준으로 합니다. 이는 Function이 HTTP 요청을 받은 정확한 시각이 아니라 Event Hubs에 enqueue된 시각이며 JSON body의 필드도 아닙니다.

코드와 unit test는 output binding에 전달한 body가 원문과 같은지까지만 검증할 수 있습니다. 실제 파이프라인에서 enqueue timestamp를 사용할 수 있으려면 consumer 또는 downstream connector가 Event Hubs system property를 읽거나 컬럼으로 투영해야 합니다. 현재 변경에서는 Azure 배포, Event Hubs 수신, downstream projection을 E2E로 검증하지 않았으므로 실제 파이프라인에서의 노출 여부는 별도 확인이 필요합니다.

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
- JSON으로 해석 불가능한 HTTP body의 Bronze 보존 형식 및 저장 여부

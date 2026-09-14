# CANOPY GPS Capture → ADLS Raw E2E Verification — 2026-09-14

## 목적

실제 iPhone에서 수집한 GPS 이벤트가 Azure Function → Event Hubs → Event Hubs Capture → ADLS Raw 경로로 저장되는지 확인한다.

## 검증 환경

- Function App: `func-canopy-gps-dev`
- Function: `GpsIngest`
- Event Hubs Namespace: `evhns-canopy-dev`
- Event Hub: `evh-canopy-gps-dev`
- Storage Account: `stcanopydev5dt`
- File System: `raw`
- Capture Encoding: Avro
- Capture Interval: 300 seconds
- Function 인증/전송: System Assigned Managed Identity + Azure Event Hubs Data Sender

## 확인 결과

- `GpsIngest` Azure 배포: Confirmed
- Function Host: Running
- 로컬 unit test: 18 passed
- 실제 iPhone GPS JSONL: 874 records
- JSON parse error: 0
- 실제 GPS 전송: 10 records
- HTTP 202: 10/10
- Event Hubs Capture 신규 Avro 생성: Confirmed
- Capture Avro에서 실제 GPS 발견: 10/10
- Capture Body JSON parse error: 0
- JSON 전체 값 일치: 9/10
- 1건 차이 필드: `received_at`

## Capture Raw 경로

`raw/gps/{Namespace}/{EventHub}/{PartitionId}/{Year}/{Month}/{Day}/{Hour}/{Minute}/{Second}.avro`

2026-09-14 실제 GPS 전송 이후 여러 Event Hub partition에 신규 Avro 파일이 생성되었고,
해당 Capture 파일에서 전송한 실제 GPS 이벤트 10건 모두 확인하였다.

## 판정

**E2E Verified** — 실제 iPhone에서 수집한 GPS 이벤트가
`GpsIngest → Event Hubs → Event Hubs Capture → stcanopydev5dt/raw`
경로로 저장되는 것을 확인하였다.

단, source JSON과 Capture Body의 bit/text-level 완전 동일성은 확인되지 않았다.
JSON 값 기준으로는 10건 중 9건이 전체 일치했고,
1건은 `received_at` 필드 차이가 관측되었다.
따라서 본 검증 결과를 “모든 필드가 100% 원본 그대로 보존됨”으로 확대 해석하지 않는다.

## 개인정보 / 보안

실제 GPS 좌표, 사용자/디바이스 식별자, Function key,
tenant/subscription ID 및 인증 정보는 문서에 기록하지 않는다.

## 남은 확인 사항

- `received_at` 1건 불일치 원인 확인
- Capture Body와 source JSON의 text-level 차이 원인 확인

위 항목은 이번 과제의 “실제 iPhone GPS가 ADLS Raw에 저장되는지” 검증 완료 여부와는 분리하여 관리한다.

# Trip 종료 후 예측 결과 대기

우리 후속 처리만 변경했다. 팀원 ML 파이프라인, 테이블, README는 수정하지 않았다.

## 처리

1. 분기된 종료 이벤트를 `register()`로 우리 Delta 대기열에 저장한다. 같은 이벤트를 다시 받아도 최초 대기 시간을 늘리지 않는다.
2. `poll()`은 확인 시간이 된 Trip들을 DataFrame으로 처리한다. 입력은 `dbw_canopy_dev.silver.gps_features`, `dbw_canopy_dev.gold.mode_segment_predictions`이다.
3. GPS의 1번부터 `expected_last_sequence`까지 누락이 없는지 확인한다. 예측은 `scored`여야 하며, 유효한 GPS 지점들과 마지막 GPS 시각을 모두 포함해야 한다. 버튼을 누른 시각과 예측 종료 시각의 단순 일치는 사용하지 않는다.
4. GPS 거리 값은 해당 지점에서 끝나는 이동 거리로 배분한다. 경계 지점은 앞 구간에 한 번만 포함하고, 유효하지 않은 이동 거리는 제외한다. 중첩 구간이나 충돌 데이터는 확정하지 않는다. `train`은 `rail`로 연결한다.
5. 준비된 입력은 `envelope_json`에 고정한다. 기존 `finalize_trip_pipeline.py`가 이를 읽어 탄소 계산, Gold 저장, Cosmos 반영을 수행한다. ML에 별도 완료 컬럼을 요구하지 않는다.

## 대기와 오류

- 기본 재확인 간격: 10초, 20초, 40초, 이후 60초. 실제 실행 간격은 호출하는 Job에 달려 있다.
- 최초 접수 후 600초 또는 확인 12회 한도. `--timeout-seconds`, `--max-attempts`로 변경한다.
- 입력 테이블 조회 실패도 같은 한도를 사용한다. 한도 이후는 `timed_out`이며 탄소를 계산하지 않는다.
- `publish-wait-failure`는 기존 Cosmos Trip이 우리 Databricks 처리에 할당된 경우에만 `failed / wait_for_ml`로 반영한다. 준비된 Trip, 다른 세대, Functions Mock 결과는 덮어쓰지 않는다.
- 아직 Cosmos에 실패를 반영하지 않은 대기열은 `retry()`로 명시적으로 재개할 수 있다. 동일 `request_id` 재전송은 대기 시간을 다시 늘리지 않는다.
- Cosmos에 실패가 반영된 뒤 앱 재시도는 기존 Stop API의 `retry_request_id`를 사용한다. 새 `processing_generation`의 종료 이벤트가 새 대기 건이 된다. 이전 세대는 최종 결과를 덮어쓰지 못한다.
- 현재 Mock 검출기는 250~300개 속도 지점으로 구간을 만든다. 마지막 미완성 묶음의 예측이 없으면 우리 쪽은 시간 초과로 남긴다. 짧은 구간을 임의로 걷기나 거리 0으로 바꾸지 않는다.

## 기존 후속 작업에 연결할 호출

`cloud/azure/pipelines/databricks/trip_prediction_wait.py`

```text
register --end-table <분기된 종료 이벤트 테이블> --queue-path <우리 Delta 대기열 경로>
poll --queue-path <동일 경로>
retry --queue-path <동일 경로> --user-id <ID> --trip-id <ID> --generation <번호> --request-id <새 요청 ID>
```

`cloud/azure/pipelines/databricks/finalize_trip_pipeline.py`

```text
finalize --ready-path <대기열 경로> --user-id <ID> --trip-id <ID> --gold-path <기존 Gold 경로>
publish --user-id <ID> --trip-id <ID> --gold-path <동일 Gold 경로> <기존 Cosmos 인증 설정>
publish-wait-failure --ready-path <대기열 경로> --user-id <ID> --trip-id <ID> <기존 Cosmos 인증 설정>
```

`register` 입력은 기존 종료 이벤트 계약의 ID, 사용자, 캠페인, 시작/종료 시각, 마지막 sequence, 처리 세대, `result_owner`를 포함한다. 시작/종료 시각은 timestamp 타입이다. 대기열은 Cosmos가 아닌 Delta에 저장한다.

## 아이폰 자동 연결 (2026-09-16)

기존 `func-canopy-dev`와 본인 Job `136906075485874`를 연결했다. 새 파이프라인은 만들지 않았다.

1. 앱 종료: 수집을 멈추고 남은 GPS 전송을 마친 뒤 마지막 sequence를 Stop API로 보낸다.
2. API: Trip과 종료 outbox를 함께 저장하고 같은 Event Hub에 `trip_ended`를 보낸다. 실패하면 같은 event_id로 재전송한다.
3. `trip_end_received`: 별도 consumer group `canopy-trip-finalization`에서 종료 이벤트만 처리한다. 인증된 Stop에 저장된 원본 이벤트와 일치해야 한다.
4. `trip_dispatch.py`: 종료 event_id를 Databricks idempotency token으로 사용해 기존 Job을 호출한다. 호출 응답이 유실돼도 같은 실행으로 재시도한다. 동시 실행은 최대 3건이며 나머지는 Job 대기열에 들어간다.
5. `trip_job.py`: 결과를 Gold에 먼저 저장하고 다시 읽어 확인한 뒤 기존 Cosmos `canopy-db/trips`에 반영한다. 앱은 같은 Trip ID를 조회해 결과를 표시한다.

현재 `TRIP_DATABRICKS_INPUT=mock`이다. 실제 GPS는 Raw까지 전송하지만 이동수단과 거리는 기존 테스트 예시(걷기 500m, 버스 6200m, 걷기 300m)다. 결과에 `is_mock=true`를 남기며 앱에도 표시한다.

ML 연결은 `TRIP_DATABRICKS_INPUT=ml`로 바꾸면 위의 실제 테이블 대기 경로를 사용한다. 팀 테이블에 앱 데이터와 마지막 예측이 있어야 성공한다. 없는 상태를 완료로 처리하지 않는다.

Gold: `abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/iphone_final_trips`

ML 대기열: 같은 경로의 `iphone_wait`. Weekly 입력은 Gold를 읽으며 Cosmos를 중간 입력으로 사용하지 않는다.

Job 시작/호출 실패도 종료 후 30분을 넘겨 기다리지 않는다. ML 입력 대기는 별도로 600초/12회 한도다. 실패하면 앱에 실패 상태를 표시하고 기존 재시도 버튼으로 새 처리 세대를 시작한다.

## 설정과 확인

- Functions: `.env.example`의 `TRIP_DATABRICKS_*`, `TRIP_EVENTHUB_*`, `TRIP_RESULT_OWNER=databricks`, `TRIP_END_EVENTS_ENABLED=true`. 비밀 값은 커밋하지 않는다.
- Functions 관리 ID: 해당 Event Hub Data Sender/Data Receiver, Databricks workspace 접근 및 본인 Job의 CAN_MANAGE_RUN 권한. Cosmos 키는 기존 Databricks Secret scope를 사용한다.
- `tools/azure/package_trip_pipeline.py --iphone`은 같은 Job 설정과 필요한 기존 모듈을 묶는다. 생성한 설정은 기존 Job에 적용하며 새 Job을 만들 필요가 없다.
- `tools/azure/package_trip_api.py`의 `patch_deployed()`는 배포된 팀 파일을 보존하고 본인 Trip 모듈만 교체한다. Linux 실행 권한도 검사한다.
- `tools/azure/check_trip_e2e.py --send-test`는 합성 Trip 두 건을 실제 API에 보낸다. 재확인은 `--send-test` 없이 실행하면 새 데이터를 보내지 않는다. GPS와 종료 이벤트의 Raw 원본, Cosmos 결과, Databricks run_id를 확인한다.

## 검증

- API 43개, 앱 14개, TypeScript 검사 통과.
- 후속 처리 17개 통과. 별도 JDK가 필요한 Weekly Spark 검증 1개는 이번 일반 검사에서 제외했다.
- 이전 Databricks 대기열 검증 Run `304357990371636`: 중복 종료, 조회 실패 재시도, 시간 초과, 명시적 재시도, 이벤트 충돌 확인.
- 실제 휴대폰 조작은 사용자가 새 QR로 앱을 열고 시작/종료해 확인한다. 데스크톱 합성 요청을 실제 iPhone 시험으로 기록하지 않는다.

- 실제 API 자동 연결 검증: 사용자용/개발자용 합성 Trip 두 건 모두 성공. Databricks Run `326666064137519`, `194034142443718`.
- GPS 4건과 종료 이벤트 2건을 Raw에서 원본 그대로 확인했다. GPS 재전송 중복도 보존했다. 두 결과 모두 Gold 재조회 후 Cosmos `ready` 및 API 응답까지 확인했다.
- 실행 준비를 포함한 Job 소요 시간은 각각 약 6분 28초, 9분 14초였다. 즉시 결과를 반환하는 운영 성능 검증은 아니다.

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

## 배포 범위

새 파이프라인은 만들지 않았다. 코드와 테스트를 본인 Databricks 테스트 영역에 올려 검증한다. 앱 종료부터 자동 실행하려면 기존 수신 분기에서 `register` 입력을 연결하고, 본인 Job에서 `poll`과 후속 성공/실패 처리를 호출해야 한다. 현재 자동 실행은 설정하지 않았다. 실제 ML의 마지막 예측을 포함한 휴대폰 E2E는 완료로 처리하지 않는다.

## 확인 결과 (2026-09-16)

- 로컬 Spark: 정상 입력을 기존 탄소 계산에 연결, 마지막 예측 누락, 중간 GPS 누락, 미완료 추론, 사용자 분리, 경계 거리 중복 방지, 시간 초과 확인.
- 기존 API 테스트 29개 통과. 기존 후속 처리 테스트는 14개 중 13개 통과, 선택 검증 1개 제외.
- Databricks 수동 검증 성공: Run `304357990371636`. Delta 대기열 저장, 종료 재전송 시 원래 기한 유지, 조회 실패 재시도, 확인 시각 전 건너뛰기, 시간 초과, 명시적 재시도, 동일 재시도 요청의 기한 연장 방지, 종료 정보 충돌 확인.
- 테스트는 합성 데이터와 `curated/pipeline_test/trip_finalization/` 하위 전용 경로만 사용했다. 실제 사용자 결과는 쓰지 않았다. 자동 실행 Job이나 새 파이프라인은 생성하지 않았다.

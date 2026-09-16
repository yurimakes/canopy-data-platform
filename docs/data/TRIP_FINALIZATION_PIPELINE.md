# Trip 최종 결과 파이프라인

Mock/최종 ML 구간 → 기존 탄소 계산 → ADLS Gold Delta → Cosmos `canopy-db/trips`.
다음 파이프라인의 Weekly가 동일한 Gold를 직접 읽을 수 있게 저장한다. `sync_confirmed_trips.py`와 Cosmos 입력은 사용하지 않는다.

## 현재 범위

- `finalize_trip_pipeline.py`: 기존 `validate_result`, `finalize_result`, 탄소 계산 모듈을 호출한다.
- `package_trip_pipeline.py`: 필요한 기존 파일만 그대로 묶고 수동 실행 Job 설정을 만든다. 배포하지 않는다.
- 이번 Job은 Gold 저장과 Cosmos 반영만 실행한다. Weekly와 Baseline은 다음 파이프라인의 범위다.
- Mock은 기존 `ConfirmationFixtureProcessor`의 걷기 500m, 버스 6200m, 걷기 300m이다. 총 7000m, 0.778224 kgCO2e.
- Mock Trip/캠페인은 `pipeline_test_` 접두사, Delta는 `/pipeline_test/` 하위로 제한한다. 운영 Weekly에 섞지 않는다.
- 기존 GPS/ML 파이프라인, Functions 배포, 팀원 계산 코드와 README는 변경하지 않는다.

## 교체할 입력

```json
{
  "provider": "external",
  "completed_at": "2026-09-16T01:11:00+00:00",
  "trip": {
    "trip_id": "trip_001",
    "user_id": "user_001",
    "campaign_id": "campaign_001",
    "status": "processing",
    "processing_generation": 1,
    "started_at": "2026-09-16T01:00:00+00:00",
    "ended_at": "2026-09-16T01:10:00+00:00"
  },
  "result": {
    "trip_id": "trip_001",
    "model_version": "team_model_v1",
    "segments": [{
      "segment_id": "trip_001:segment:1",
      "mode": "bus",
      "start_time": "2026-09-16T01:00:00+00:00",
      "end_time": "2026-09-16T01:10:00+00:00",
      "distance_m": 6200,
      "confidence": 0.9
    }]
  }
}
```

`result`는 기존 `apps/api/services/trip_processor.py`의 `ProcessorResult` 계약이다.
ML팀은 이 부분을 공급하고 `provider`를 `external`로 바꾼다. `start_time/end_time` 이름을 사용한다.
`trip`은 신뢰할 수 있는 시작/종료 이벤트에서 공급해야 한다. ML이 사용자나 캠페인을 정하지 않는다.
`completed_at`과 `processing_generation`은 재시도 시 유지한다.

## 저장과 재시도

Gold는 `(user_id, trip_id)`당 최신 generation 한 행을 저장한다. 같은 generation의 다른 결과는 오류다.
한 Job의 동시 실행 수는 1이다. 같은 Gold 경로를 여러 Job이 동시에 쓰지 않는다.
`segments`, `carbon` 등 Weekly 입력 열과 전체 Cosmos 결과 `document_json`, `finalization_hash`를 보존한다.
거리 단위는 m, 탄소 단위는 kgCO2e다. Cosmos 반영은 반드시 저장된 Gold를 다시 읽는다.
Cosmos 실패 시 `publish_cosmos` 작업만 재실행한다. 기존 탄소 계산이나 ML을 다시 실행하지 않는다.
기존 Cosmos Trip은 같은 generation이고 `status=processing`, `result_owner=databricks`여야 한다.
이미 Functions가 처리한 결과는 덮어쓰지 않으며, 다른 필드와 피드백은 유지한다.

## 아직 연결하지 않은 부분

이 Job은 별도 수동 검증용이다. 현재 휴대폰 종료 요청이 이 Job을 자동 실행하지 않는다.
운영 연결에는 Trip 종료 이벤트 전달, Functions 계산 실행권 이관, ML 최종 구간 완성 확인이 필요하다.
기존 Functions를 유지한 채 `result_owner`만 바꾸면 안 된다. 두 처리기가 동시에 계산할 수 있다.
Weekly 운영 입력의 출퇴근 판정 및 Mock 제외 정책도 기존 담당자와 연결해야 한다.

Databricks의 ADLS 접근 권한이 Cosmos 권한을 뜻하지 않는다.
실행 환경에 준비된 Azure 자격 증명을 사용하거나, 승인 후 Secret scope의 Cosmos 키를 연결한다.
키를 코드, Job 인자, Git에 직접 넣지 않는다. 리소스와 역할은 이 코드가 만들지 않는다.

## 로컬 확인

```powershell
.\apps\api\.venv\Scripts\python.exe -m unittest discover -s tests/integration -p test_trip_finalization_pipeline.py -v
```

실제 Databricks 검증 결과는 아래에 기록한다.

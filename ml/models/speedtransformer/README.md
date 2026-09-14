# SpeedTransformer 런타임 연동

Canopy에서 등록된 AI Hub speed-only SpeedTransformer champion 모델을 사용하는 런타임 연동 영역입니다.

모델 개발의 기준 저장소(source of truth)는 `aletheia-ops/speedtransformer-aihub`입니다. 이 디렉터리에는 Canopy에서 필요한 런타임 계약과 MLflow / Unity Catalog 연동 코드만 둡니다.

## 디렉터리 구조

- `configs/`: 레지스트리 및 런타임 계약 메타데이터
- `inference/`: MLflow / Unity Catalog 모델 로드 및 추론 호출 코드
- `features/`: Canopy 측 feature/window 생성 로직. segment를 200개 point로 변환하는 정책이 확정되기 전까지 비워 둡니다.
- `tests/`: 런타임 계약 및 parity 테스트

## 고정 입력 계약

- 추론 1행은 `speed_sequence` 1개를 가집니다.
- 단위: km/h
- 길이: 정확히 200개
- 모든 값은 finite value여야 합니다.
- 허용 범위: `0 <= speed <= 200`
- 출력 class: `bike`, `bus`, `car`, `train`, `walk`

등록된 MLflow 패키지가 StandardScaler 적용, 모델 구조 복원, checkpoint 로드, class decoding을 담당합니다. Canopy 저장소에서는 scaler 또는 label encoder를 별도로 구현하거나 Git에 복제하지 않습니다.

## 이 저장소에 저장하지 않는 항목

- `best_macro_model.pth`
- `scaler.joblib`
- `label_encoder.joblib`
- 학습 데이터셋
- 실험 보고서 및 ablation 실행 스크립트

위 binary artifact는 MLflow / Unity Catalog가 관리하고, 학습 및 연구 이력은 `speedtransformer-aihub`에 유지합니다.

## Window 정책 미확정 사항

현재 champion 모델은 정확히 200개의 transition을 요구합니다. 따라서 다음 경우에 대한 Canopy 정책을 별도로 확정해야 합니다.

- 확정된 segment가 200 point보다 긴 경우
- 확정된 segment가 200 point보다 짧은 경우
- trip 종료 시 남은 segment의 flush/fallback 처리

정책이 확정되고 테스트되기 전에는 임의 padding, truncation, aggregation을 적용하지 않습니다.

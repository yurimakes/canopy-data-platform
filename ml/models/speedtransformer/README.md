# SpeedTransformer 런타임 / Playground

Canopy에서 사용하는 AI Hub speed-only SpeedTransformer champion 모델의 런타임 연동 및 팀원용 playground 영역입니다.

모델 개발의 기준 저장소(source of truth)는 `aletheia-ops/speedtransformer-aihub`입니다. 이 디렉터리는 Canopy 서비스 연동과 로컬 실습에 필요한 최소 구성만 보관합니다.

## 기본 원칙

- **기본 실행은 로컬**이며 Azure/Databricks 인증이 필요하지 않습니다.
- `artifacts/playground_v1/`에 로컬 MLflow snapshot을 둘 수 있습니다.
- MLflow Registry / Unity Catalog 사용은 선택 사항입니다.
- 운영 모델 source of truth는 registry로 유지하고, Git의 local snapshot은 팀 개발·데모용으로 봅니다.
- 학습 코드, 전체 학습 데이터, ablation 결과는 `speedtransformer-aihub`에 유지합니다.

## 디렉터리 구조

```text
speedtransformer/
├── README.md
├── artifacts/
│   ├── README.md
│   └── playground_v1/        # export 후 추가 가능한 로컬 MLflow snapshot
├── configs/
│   └── champion_v1.json
├── features/                 # 200-point 생성 정책 확정 후 구현
├── inference/
│   ├── predict_cli.py
│   └── registry.py
└── tests/
```

샘플 입력은 `data/fixtures/speedtransformer/`에서 생성합니다.

## 입력 계약

- 입력 컬럼: `speed_sequence`
- 단위: km/h
- 길이: 정확히 200개
- 모든 값은 finite value
- 허용 범위: `0 <= speed <= 200`
- 출력 class: `bike`, `bus`, `car`, `train`, `walk`

MLflow 패키지가 StandardScaler 적용, 모델 구조 복원, checkpoint 로드, class decoding을 담당합니다. Canopy 코드에서 이 전처리를 다시 구현하지 않습니다.

## 로컬 실행

의존성 설치:

```bash
pip install -r ml/requirements.txt
```

smoke 입력 생성:

```bash
python data/fixtures/speedtransformer/generate_smoke_input.py > /tmp/speedtransformer_smoke.json
```

로컬 artifact가 `artifacts/playground_v1/`에 준비되어 있다면:

```bash
python ml/models/speedtransformer/inference/predict_cli.py \
  --input /tmp/speedtransformer_smoke.json
```

다른 로컬 MLflow model directory를 사용할 수도 있습니다.

```bash
python ml/models/speedtransformer/inference/predict_cli.py \
  --input /tmp/speedtransformer_smoke.json \
  --model-path /path/to/mlflow/model
```

## 선택 사항: Registry 모델 사용

필요한 환경에서만 registry URI를 전달합니다.

```bash
python ml/models/speedtransformer/inference/predict_cli.py \
  --input /tmp/speedtransformer_smoke.json \
  --model-uri 'models:/<catalog>.<schema>.speedtransformer@champion'
```

이 경로는 로컬 playground의 필수 조건이 아닙니다.

## Strict candidate (별도 MLflow run)

`inference/log_strict_candidate.py`는 외부 `speedtransformer_strict_v1_artifact.zip`의
SHA256을 검증하고, 기존 `artifacts/playground_v1/code/model_utils.py`의
`TrajectoryTransformer`를 재사용하는 pyfunc를 MLflow Tracking에 기록합니다.
ZIP과 `model.pt`는 Git에 추가하지 않습니다.

```bash
python ml/models/speedtransformer/inference/log_strict_candidate.py \
  --artifact-zip /path/to/speedtransformer_strict_v1_artifact.zip
```

출력된 모델 URI를 기존 GPS streaming bundle의 `model_uri` 변수에 지정하면
`segment_inference.py`의 `speed_sequence[200]` 계약을 그대로 사용합니다.
기본값인 팀 `canopy_speedtransformer@champion` alias는 변경하지 않습니다.
이 candidate는 `bike, bus, car, train, walk` 순서로 확률을 반환하며,
`SUBWAY`는 서비스 클래스 `train`으로 변환합니다.

## Playground artifact 생성

`speedtransformer-aihub` 저장소의 `scripts/export_playground_model.py`를 사용해 생성합니다. 해당 스크립트는 외부 cloud 연결 없이 checkpoint/scaler/label encoder hash를 검증하고 MLflow snapshot을 export한 뒤 smoke parity를 검사합니다.

예시 출력 위치:

```text
../canopy-data-platform/ml/models/speedtransformer/artifacts/playground_v1
```

실제 snapshot을 Git에 추가하기 전에는 디렉터리 크기를 확인합니다. 작은 단일 champion snapshot만 유지하고 과거 모델을 계속 누적하지 않습니다.

## Window 정책 미확정 사항

현재 champion 모델은 정확히 200개의 transition을 요구합니다. 따라서 다음 경우는 별도 정책이 필요합니다.

- 확정 segment가 200 point보다 긴 경우
- 확정 segment가 200 point보다 짧은 경우
- trip 종료 시 남은 segment의 flush/fallback 처리

정책이 확정되고 테스트되기 전에는 임의 padding, truncation, aggregation을 적용하지 않습니다.

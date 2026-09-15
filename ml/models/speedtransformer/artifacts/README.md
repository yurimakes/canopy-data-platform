# SpeedTransformer 로컬 아티팩트

이 디렉터리는 팀 개발·데모·playground 용도의 **로컬 MLflow 모델 snapshot**을 둘 수 있습니다.

권장 경로:

```text
artifacts/
├── README.md
└── playground_v1/
    ├── MLmodel
    ├── artifacts/
    ├── code/
    └── ...
```

## 원칙

- 기본 로컬 실행은 Azure/Databricks 인증을 요구하지 않습니다.
- `playground_v1`은 운영 source of truth가 아니라 팀용 snapshot입니다.
- 운영 모델의 source of truth는 MLflow Model Registry / Unity Catalog로 유지합니다.
- 로컬 snapshot과 운영 모델은 동일한 champion checkpoint SHA-256으로 연결합니다.
- 모델이 교체될 때 기존 snapshot을 무제한 누적하지 않고 필요한 버전만 유지합니다.

## 현재 champion 원본 SHA-256

- checkpoint: `f72e918051c20ad3b4b3e6eb0bae3ba235b0155e3a33079ffb334a8d97840d06`
- scaler: `6485499bb01ac9f506df5a6a897e6529a3237b9e813ed567b99780d8e058b867`
- label encoder: `29119f4d7acde3eac5a113a7a887eb3b4aade771a1b23c9ca2fdb9137e3a14f6`

실제 `playground_v1/`은 `speedtransformer-aihub`의 export script로 생성한 뒤 크기를 확인하고 커밋합니다.

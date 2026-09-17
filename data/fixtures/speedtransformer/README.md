# SpeedTransformer 샘플 데이터

이 디렉터리는 Azure/Databricks 없이 로컬에서 SpeedTransformer 추론을 재현하기 위한 작은 fixture를 보관합니다.

기본 smoke fixture는 학습 시 사용한 `StandardScaler`의 평균 속도 `23.33237837 km/h`를 200개 반복한 입력입니다.

```text
speed_sequence = [23.33237837] * 200
```

기대 결과:

- class: `bike`
- confidence: 약 `0.991168`

실제 200개 값을 저장소에 반복해서 기록하지 않고 `generate_smoke_input.py`로 생성합니다.

```bash
python data/fixtures/speedtransformer/generate_smoke_input.py > /tmp/speedtransformer_smoke.json
```

생성된 JSON은 `ml/models/speedtransformer/inference/predict_cli.py`의 입력으로 사용할 수 있습니다.

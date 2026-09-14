# Azure 도구

Azure 설정, 검증, 마이그레이션, 로컬 CLI 보조 도구를 둡니다. 실제 인프라 정의는 `cloud/azure/`에 둡니다.

Trip API 패키징과 실제 Azure 재검증은 [apps/api 실행 안내](../../apps/api/README.md)를 참고하세요. `check_trip_e2e.py`는 기본적으로 기존 결과를 조회하고, `--send-test`를 지정할 때만 합성 Trip/GPS를 전송합니다.

# Baseline Eligibility 연결

Personal은 7일 이상 관측하고 확정 출퇴근 Trip 6개 이상, 거리 양수, 탄소 유효값일 때 계산합니다. Global은 같은 캠페인의 Personal-ready 사용자 6명 이상일 때 계산합니다. 부족하면 collecting, value=null입니다. 탄소 0은 유효값입니다.

## 코드

| 위치 | 역할 |
|---|---|
| `shared/configs/baseline_eligibility.yaml` | 7일, 6회, 6명 정책 |
| `cloud/azure/pipelines/databricks/baseline_eligibility.py` | 조건 검사와 가입일 조회 |
| `build_personal_baseline.py` | 기존 누적 계산 직전에 검사 |
| `build_global_baseline.py` | ready 사용자만 골라 기존 평균 계산 호출 |
| `run_eligible_baselines.py` | 코드와 함께 배포한 YAML로 실행 |

위 세 Python 파일의 경로는 `cloud/azure/pipelines/databricks/`입니다. 기존 `build_weekly_summary.py`, `sync_confirmed_trips.py`, Weekly Job JSON과 `baseline_policy.yaml`은 변경하지 않았습니다. Personal의 과거 누적 탄소/과거 누적 거리 공식과 Global의 Personal 동일 가중 평균은 유지했습니다.

## 사용자와 캠페인 참여일

2026-09-15에 승인받아 기존 `cosmos-canopy-dev / canopy-db`에 다음 컨테이너를 추가했습니다. 기존 Serverless 계정을 사용하며 처리량을 따로 예약하지 않았습니다.

| 컨테이너 | partition key | 문서 id | 기준 날짜 |
|---|---|---|---|
| `users` | `/user_id` | user_id | created_at |
| `campaign_memberships` | `/user_id` | campaign_id | joined_at |

스키마는 `shared/schemas/user.schema.json`, `shared/schemas/campaign_membership.schema.json`입니다. 회원가입 API와 캠페인 참여 API가 서버 시각을 저장해야 합니다. 이번 작업은 계정 생성, 로그인, 비밀번호 저장을 구현하지 않습니다. 날짜를 임의로 채운 실제 사용자 문서도 만들지 않았습니다.

조회 순서는 해당 캠페인의 `campaign_joined_at` 또는 `joined_at`, 없으면 사용자 `joined_at` 또는 `created_at`입니다. 날짜가 없거나 잘못됐으면 collecting입니다. 다른 캠페인의 참여일이나 Trip 시작 시각으로 대체하지 않습니다.

평가는 기존 주간 스냅샷에 맞춰 해당 ISO 주 월요일 00:00 UTC 기준입니다. 관측일은 가입 시각부터 경과한 완전한 24시간 수입니다. 계산에 쓰는 Trip 수도 기존 공식과 같은 이전 주까지의 누적 합계입니다. 과거 스냅샷 재실행에 오늘 날짜를 적용하지 않습니다.

## 현재 실제 연결이 남은 부분

1. 현재 Weekly Gold는 확정된 전체 Trip을 집계합니다. 출퇴근 전용임이 확인되기 전에는 `CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED=true` 또는 `--confirmed-commute-only`를 설정하면 안 됩니다. 유진님과 출퇴근 데이터 범위를 먼저 맞춰야 합니다. Weekly 코드는 이 작업에서 수정하지 않았습니다.
2. 사용자와 참여 정보 컨테이너는 생성했지만 가입 기능이 날짜를 저장해야 합니다. 데이터가 없는 사용자는 계산되지 않습니다.
3. 조사 시점에 Databricks에 등록된 Job과 Git Folder는 없었습니다. 별도 노트북 실행과 `dbfs:/canopy/jobs`를 가리키는 Job 예시만 있었습니다. 기존 노트북 옆에 Git YAML이 있다고 가정하지 않았습니다.
4. 이 브랜치의 Databricks Job 배포와 실제 계산 실행은 하지 않았습니다. 로컬 Spark 계산과 별도 디렉터리로 풀어 놓은 배포 묶음의 YAML 읽기를 검증했습니다.

## 창연님 연결 순서

1. 이 브랜치의 변경을 검토해서 반영합니다. 구버전 Baseline PR을 함께 덮어쓰지 않습니다. 기준은 main에 들어온 `cloud/azure/pipelines/databricks/build_personal_baseline.py`와 `build_global_baseline.py`입니다.
2. 기존 실행 순서를 **Weekly Gold → Personal → Global → Cosmos 저장**으로 연결합니다. 기존 Job 예시의 Global은 Weekly에만 의존하므로, 생성되는 task fragment를 참고해 Personal 완료 후 실행되게 바꿔야 합니다. Weekly 작업 자체는 그대로 둡니다.
3. 가입일 조회에 `CANOPY_COSMOS_ENDPOINT`, `CANOPY_COSMOS_DATABASE=canopy-db`를 설정합니다. 기본 컨테이너는 users와 campaign_memberships입니다. 인증은 기존 환경의 `CANOPY_COSMOS_KEY` 또는 DefaultAzureCredential을 사용합니다. 키를 소스에 적지 않습니다. Databricks 실행 주체에 두 컨테이너 읽기 권한이 필요합니다. 테스트 입력은 `--identities-file`로 기존 사용자/참여 레코드의 JSON 묶음을 줄 수도 있습니다.
4. 출퇴근 전용 입력임을 확인한 후 Personal에 `--confirmed-commute-only`를 전달합니다. 실제 Weekly 필드 `trip_count`, `total_distance_m`, `total_kg_co2e`를 그대로 읽습니다.
5. Cosmos 저장 코드에서 값으로 상태를 다시 추정하지 말고 `status`, `value`, `eligibility_policy_version`, Global의 `eligible_participant_count`를 보존합니다. 기존 `policy_version`은 계산 정책 버전으로 유지합니다. 현재 별도 runtime-integration 브랜치의 Global writer는 null을 insufficient_data로 바꾸므로 collecting 보존과 새 필드 전달을 연결해야 합니다. 그 브랜치는 수정하거나 복사하지 않았습니다.
6. 가입일이 있는 테스트 사용자의 7일/6회와 같은 캠페인의 ready 5명/6명을 실행해 Delta와 Cosmos의 상태 및 null을 확인합니다. 기존 스냅샷에 eligibility 정보가 없으면 Personal부터 다시 평가합니다.

## YAML 배포 방법

2026-09-15에 기존 Storage에 정책 YAML을 업로드하고 다운로드한 바이트가 원본과 같은지 확인했습니다. 새 Storage 계정이나 컨테이너는 만들지 않았습니다.

```text
abfss://curated@stcanopydev5dt.dfs.core.windows.net/config/baseline/eligibility-v1/baseline_eligibility.yaml
```

Job에 `--eligibility-policy`로 위 경로를 전달하거나 `CANOPY_BASELINE_ELIGIBILITY_PATH`에 설정합니다. Databricks의 기존 Storage 권한으로 읽습니다. 권한 오류나 파일 누락 시 로컬 정책으로 바꾸지 않고 실패합니다. 업로드 확인과 Databricks 실행 확인은 별개이며, 실제 Job 실행은 아직 하지 않았습니다.

코드는 다음 묶음으로 배포할 수 있습니다.

```powershell
python tools/azure/package_baseline_eligibility.py --workspace-root /Workspace/Shared/canopy-baseline
```

위 경로는 배포할 때 선택하는 예시이며 현재 생성한 경로가 아닙니다. 결과는 `data/interim/baseline-eligibility.zip`입니다. ZIP을 풀고 내부 디렉터리 구조 그대로 Workspace **파일**로 업로드하거나, 같은 저장소의 Git Folder에서 실행합니다. `.py`를 notebook으로 변환하지 않습니다. 이 도구는 업로드나 Job 생성은 하지 않습니다.

예시 배포 루트가 `/Workspace/Shared/canopy-baseline`이면 YAML은 `/Workspace/Shared/canopy-baseline/shared/configs/baseline_eligibility.yaml`이고 실행 파일은 그 아래 `cloud/azure/pipelines/databricks/run_eligible_baselines.py`입니다. `__file__` 기준으로 찾으므로 현재 작업 디렉터리에 의존하지 않습니다. 필요하면 `CANOPY_BASELINE_ELIGIBILITY_PATH`로 명시합니다. 경로가 없으면 기본 숫자로 대체하지 않고 실패합니다.

```text
run_eligible_baselines.py --check-config
run_eligible_baselines.py --phase personal --campaign-id CAMPAIGN --confirmed-commute-only
run_eligible_baselines.py --phase global --campaign-id CAMPAIGN --evaluation-week 2026-W38
```

두 번째 명령의 출퇴근 확인 옵션은 데이터 범위 확인 후에만 사용합니다. Spark 4 또는 호환 Databricks Spark Connect에서 실행합니다. driver가 YAML을 읽고 policy 객체를 전달하며 Python 모듈은 `addArtifact(..., pyfile=True)`로 executor에 배포합니다. [Spark 공식 문서](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.SparkSession.addArtifact.html).

## 테스트

```powershell
python -m pip install -r cloud/azure/pipelines/databricks/requirements-test.txt
$env:CANOPY_TEST_SPARK = "1"
$env:PYSPARK_PYTHON = (Get-Command python).Source
$env:PYTHONPATH = (Resolve-Path cloud/azure/pipelines/databricks).Path
python -m unittest discover -s tests/integration -p "test_baseline*.py" -v
```

Java 17 또는 21 전체 JDK와 JAVA_HOME이 필요합니다. `CANOPY_TEST_SPARK`를 생략하면 Spark 검증은 건너뛰므로 통합 테스트 완료로 보면 안 됩니다. A~H, 기존 계산값, 중복 사용자, 다른 캠페인 제외, 날짜 누락, YAML 배포 경로를 검사합니다.

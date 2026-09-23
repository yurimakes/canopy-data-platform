# HGB sandbox 5dt024: 공동 배포 설정

이 폴더는 운영 번들과 별개의 HGB 테스트 번들입니다. 메인 워크스페이스의 sandbox에 배포하고 합성 GPS로 수집 및 분석을 검증했습니다. 실행 증거는 SMOKE_TEST_REPORT.json을 참고합니다.

## 팀 공통 구조

- 번들 이름: `canopy-hgb-sandbox-5dt024` (담당자가 바뀌어도 이름을 바꾸지 않습니다.)
- 대상: `sandbox` (운영 번들의 `trial`과 구분합니다.)
- 워크스페이스: `https://adb-7405612422597045.5.azuredatabricks.net`
- 로컬 인증 프로필: `CANOPY_TRIAL` (각 팀원이 자신의 계정으로 인증합니다.)
- 공용 배포 상태 경로: `/Workspace/bundles/.bundle/canopy/${bundle.name}/${bundle.target}`
- 공용 catalog 변수: `../../shared/variables.yml`
- Job 및 Pipeline 정의: `resources/*.yml`

저장소 전체를 받아야 shared 설정을 찾을 수 있습니다. 이 폴더만 단독 복사하지 않습니다. 기존 ZIP은 이 설정 변경 이전 버전입니다.

## 권한과 실행 계정

`users: CAN_MANAGE`는 두 Job에만 적용합니다. 번들 전체와 Pipeline에는 permissions를 선언하지 않습니다. 이는 ingestion 번들의 최신 팀 설정과 같은 방식이며, Pipeline 소유권을 배포자에게 이전하려는 permissions 요청을 방지합니다.

Job의 run_as는 `${workspace.current_user.userName}`입니다. 고정된 다른 사용자를 사칭하는 권한 없이 배포할 수 있도록 팀의 배포자 실행 방식과 맞췄습니다. 따라서 다른 팀원이 다시 배포하면 두 Job의 실행 계정도 그 배포자로 바뀝니다. 동일 Job ID를 공동 관리하는 것과 실행 계정 고정은 서로 다른 문제입니다.

Pipeline의 run_as/owner는 이 번들에서 재설정하지 않습니다. 최초 생성 시 실제 소유자 및 실행 계정을 확인하고, 다른 팀원의 공동 수정 전에 Pipeline CAN_MANAGE, 실행 계정의 데이터/secret 권한, 공용 상태 폴더 쓰기 권한을 확인해야 합니다. 기존 운영 Pipeline의 ACL이 새 Pipeline에 자동 복사되는 것은 아닙니다. 필요한 최초 ACL은 관리자 또는 소유자가 별도로 설정합니다.

항상 같은 실행 계정을 유지하는 운영 정책이 필요하면 공용 Service Principal과 팀원의 사용 권한을 먼저 준비한 뒤 전환합니다. 개인 이메일을 무조건 고정해서 다른 팀원의 배포 권한 문제를 만드는 방식은 사용하지 않았습니다.

공식 실행 계정 참고: https://docs.databricks.com/aws/en/dev-tools/bundles/run-as

## 분리된 테스트 자원

- Event Hub: `evhns-canopy-dev` / `evh-canopy-sandbox-5dt024`
- 스키마: `dbw_canopy_trial.sandbox`
- 테이블 접두사: `m5dt024_`
- 수집 Job: `sandbox_ingestion_job`, 기본 PAUSED
- 분석 Job: `sandbox_hgb_trip`, 예약/연속 실행 없이 trip_id와 user_id를 지정해 수동 실행
- Pipeline: `sandbox_ingestion`

Job 2개와 Pipeline 1개를 새로 만드는 설정입니다. 운영 Job/Pipeline ID를 bind하지 않습니다. 운영 Cosmos 및 보상에는 연결하지 않습니다.

## 이번 단계에서 가능한 확인 명령

이 번들 폴더에서 실행합니다. 아래 두 명령은 배포가 아닙니다.

```powershell
databricks bundle validate -t sandbox
databricks bundle plan -t sandbox
```

최초 배포 전 예상 plan은 `5 to add, 0 to change, 0 to delete`입니다. 5건은 Job 2개, Job 권한 2건, Pipeline 1개입니다. Pipeline permissions 자원이 나오면 안 됩니다. 다른 사람의 실제 재배포 검증은 최초 배포와 권한 설정 후 별도로 수행해야 합니다.

## 모델 검증 범위

HGB 모델과 16개 피처, 기존 Transit Context 참조 데이터, 탄소 계산 코드를 포함합니다. `python tests/test_bundle.py`로 로컬 테스트를 실행할 수 있습니다. 모델과 추론 코드는 이번 설정 정리에서 변경하지 않았습니다.

이 번들은 선택한 여정을 수동 분석하는 샌드박스입니다. 운영 resident worker 전체를 복제한 것은 아닙니다. 120초 미만의 미완성 구간은 분석하지 않고 quality 결과에 남깁니다. 서버리스 실행, 합성 Event Hub 수집 및 Delta 저장은 검증했습니다. 실제 휴대전화 정확도와 타 계정 재배포는 아직 검증하지 않았습니다.

## 실제 테스트 절차

수집은 자동 반복 대신 PAUSED 상태에서 `bundle run -t sandbox sandbox_ingestion_job`으로 필요한 횟수만 수동 실행합니다. 최초 Pipeline 실행은 최신 Event Hub offset을 초기화하므로, 초기화 완료 후 테스트 이벤트를 보내고 다시 수집을 실행합니다. 다른 팀원도 이벤트를 보내기 전에 초기화 여부를 확인합니다.

`scripts/send_sandbox_smoke.py`는 전용 Event Hub 이름과 메인 구독을 고정한 합성 이벤트 전송기입니다. `azure-eventhub`와 Azure CLI가 필요합니다. 기본은 파일 생성만 하고, `--send`를 명시해야 전송합니다. 전송 시 기존 namespace 인증 정보를 메모리에서만 사용하며 출력이나 결과 파일에 저장하지 않습니다. 실제 휴대전화 GPS가 아닙니다.

```powershell
python scripts/send_sandbox_smoke.py --output "$env:TEMP/canopy-hgb-smoke.json"
# JSON과 대상 확인 후에만 실제 전송
python scripts/send_sandbox_smoke.py --send --output "$env:TEMP/canopy-hgb-smoke.json"
databricks bundle run -t sandbox sandbox_ingestion_job
# 전송기가 출력한 실제 ID를 사용
databricks bundle run -t sandbox sandbox_hgb_trip --params "trip_id=실제테스트ID,user_id=실제테스트사용자ID"
```

분석 Job은 GPS 순번 누락을 검사하고, Delta MERGE 후 같은 사용자/여정/세대의 결과를 다시 읽어 계산 결과와 같은지 확인합니다. 저장 건수가 1개인지 함께 로그에 남깁니다. Run 성공은 합성 입력으로 전체 경로가 동작한다는 증거이며, 실제 이동수단 정확도나 앱 연결 검증을 대체하지 않습니다.


## 팀원 인계

저장소 최신 main을 받은 뒤 아래 경로에서 작업합니다. 새 번들 이름이나 개인별 root_path를 만들지 않습니다.

```powershell
cd bundles/hgb-sandbox-5dt024
databricks bundle summary -t sandbox
databricks bundle plan -t sandbox
```

현재 연결되어야 하는 ID:

| 자원 | ID |
|---|---|
| sandbox_ingestion_job | 288158402366685 |
| sandbox_hgb_trip | 1025081607321226 |
| sandbox_ingestion | e8a79548-9c8d-4fbb-979c-ccef0eab744b |

다른 계정의 plan에서는 Job 실행 계정과 Job 권한 변경이 나타날 수 있습니다. 기존 ID가 유지되고 생성/삭제가 0인지 확인합니다. Pipeline permissions 변경은 없어야 합니다. 실제 타 계정 배포 권한은 해당 계정에서 검증해야 합니다. 동시 배포는 피합니다.

## 휴대전화 연결 범위

현재 번들은 Function API 및 Cosmos 게시 기능을 포함하지 않습니다. 따라서 운영 API의 Job ID만 이 테스트 Job으로 교체하면 앱 연결이 완료되는 구조가 아닙니다. 수동 분석 인자는 trip_id/user_id이고, 기존 Function의 일반 Job 호출 인자(end_event/input_mode)와 다릅니다. 휴대전화로 종단간 시험하려면 GPS와 종료 이벤트를 함께 테스트 Hub로 라우팅하고, 수집 완료 후 분석을 실행하며, 결과를 앱이 읽는 API 형식으로 반환하는 테스트 경로가 추가로 필요합니다.

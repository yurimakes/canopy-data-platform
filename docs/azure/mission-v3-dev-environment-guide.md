# Mission v3.2 현재 dev 환경 설정 가이드

작성일: 2026-09-16
대상 브랜치: `fix/mission-v3-service-contract`
정책 버전: `mission-policy-v3.2`

## 1. 현재 Cosmos 구조에 대한 적용 결정

현재 dev Cosmos DB `canopy-db`에는 `missions`, `mission_events` 등 기존 컨테이너가 이미 존재한다. 기존 컨테이너의 partition key/소유 목적을 바꾸지 않는다.

Mission v3.2의 latest profile과 weekly bundle은 같은 partition key(`/pk`)와 같은 사용자·캠페인 접근 경계를 사용하므로 dev에서는 새 물리 컨테이너 하나를 함께 사용할 수 있다.

권장 물리 컨테이너:

```text
Database: canopy-db
Container: mission-state
Partition key: /pk
```

문서 partition key 값:

```text
pk = campaign_id + ':' + user_id
```

두 논리 컨테이너 환경변수를 같은 물리 컨테이너에 연결한다.

```text
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER=mission-state
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER=mission-state
```

이 설정은 코드 변경 없이 지원된다. 문서 `type`과 `id`가 서로 다르므로 profile과 bundle이 같은 컨테이너에 공존할 수 있다.

기존 `missions`와 `mission_events`는 재사용하지 않는다. 특히 기존 컨테이너가 `/user_id` 등의 다른 partition key를 사용한다면 현재 Mission v3.2 point-read 계약(`/pk`)과 호환되지 않는다.

## 2. Function App 환경변수

기존 `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `TRIP_CAMPAIGN_ID`는 재사용한다. 같은 값을 `CANOPY_*` 이름으로 중복 저장할 필요가 없다.

추가:

```text
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER=mission-state
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER=mission-state
CANOPY_CAMPAIGN_TIMEZONE=Asia/Seoul
CANOPY_ALLOW_DEV_USER_HEADER=true   # 통합 검증 중에만
```

통합 검증을 실제 Trip campaign과 분리하려면 임시 override를 추가할 수 있다.

```text
CANOPY_CAMPAIGN_ID=mission-e2e-20260916
```

Mission API는 `CANOPY_CAMPAIGN_ID`가 없으면 기존 `TRIP_CAMPAIGN_ID`를 사용한다. 검증 완료 후 임시 `CANOPY_CAMPAIGN_ID`를 삭제하면 Trip과 Mission이 다시 같은 campaign id를 사용한다.

검증 완료 후 반드시:

```text
CANOPY_ALLOW_DEV_USER_HEADER=false
```

## 3. Databricks에서 말하는 '설정'

Function App Configuration과 Databricks 환경은 서로 별개다. Function App에 추가한 환경변수는 Databricks cluster/job에서 자동으로 보이지 않는다.

Mission Profile Python 모듈은 다음 값을 Databricks driver의 OS environment에서 읽는다.

```text
CANOPY_GOLD_WEEKLY_USER_PATH
CANOPY_GOLD_MISSION_PROFILE_PATH
CANOPY_GOLD_MISSION_RESPONSE_PATH
CANOPY_COSMOS_ENDPOINT
CANOPY_COSMOS_DATABASE
CANOPY_COSMOS_MISSION_PROFILE_CONTAINER
CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER
CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK
CANOPY_CAMPAIGN_TIMEZONE
```

검증 notebook에서는 import 전에 `os.environ[...]`로 명시할 수 있다.

예:

```python
import os

os.environ['CANOPY_GOLD_WEEKLY_USER_PATH'] = 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/weekly_summary_user/'
os.environ['CANOPY_GOLD_MISSION_PROFILE_PATH'] = 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/mission_profile/'
os.environ['CANOPY_GOLD_MISSION_RESPONSE_PATH'] = 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/mission_response_weekly/'
os.environ['CANOPY_COSMOS_ENDPOINT'] = '<same Cosmos endpoint used by Function App>'
os.environ['CANOPY_COSMOS_DATABASE'] = 'canopy-db'
os.environ['CANOPY_COSMOS_MISSION_PROFILE_CONTAINER'] = 'mission-state'
os.environ['CANOPY_COSMOS_MISSION_ASSIGNMENT_CONTAINER'] = 'mission-state'
os.environ['CANOPY_ALLOW_COSMOS_MISSION_HISTORY_FALLBACK'] = 'true'  # Response Gold 준비 전 검증만
os.environ['CANOPY_CAMPAIGN_TIMEZONE'] = 'Asia/Seoul'
```

Job/cluster 장기 설정은 Compute/Job compute의 Environment variables에 같은 값을 넣는다.

## 4. Databricks → ADLS 인증

ADLS는 기존 Unity Catalog Storage Credential + External Location/Access Connector 경로를 계속 사용한다. Mission 작업을 위해 Storage Account key를 새로 넣지 않는다.

검증 전에 test path가 기존 External Location 범위 안에 있는지 확인한다.

## 5. Databricks → Cosmos 인증

ADLS용 Storage Credential과 Cosmos 같은 외부 Azure service용 Service Credential은 다른 개념이다.

권장 방식:

1. 기존 Azure Databricks Access Connector의 managed identity에 Cosmos `Cosmos DB Built-in Data Contributor` 데이터 평면 권한을 부여한다.
2. Databricks Catalog → External data → Credentials → Create credential → `Service Credential`을 선택한다.
3. 기존 Access Connector resource ID를 넣고 예를 들어 `canopy-azure-services`라는 Service Credential을 만든다.
4. 해당 Service Credential을 검증 사용자/job identity가 사용할 수 있도록 `ACCESS` 권한을 준다.
5. Databricks compute → Edit → Advanced → Spark → Environment variables에 다음을 추가한다.

```text
DATABRICKS_DEFAULT_SERVICE_CREDENTIAL_NAME=canopy-azure-services
```

그러면 Mission Profile 코드의 `DefaultAzureCredential()`이 Databricks Service Credential을 통해 Azure token을 얻을 수 있다. Cosmos key/connection string/client secret을 notebook 코드에 넣지 않는다.

## 6. 권장 검증용 경로

운영 Gold를 덮어쓰지 않도록 먼저 test Delta path를 사용한다.

```text
CANOPY_CONFIRMED_TRIPS_PATH=abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/confirmed_trips/
CANOPY_GOLD_WEEKLY_USER_PATH=abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/weekly_summary_user/
CANOPY_GOLD_WEEKLY_CAMPAIGN_PATH=abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/weekly_summary_campaign/
CANOPY_GOLD_MISSION_PROFILE_PATH=abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/mission_profile/
CANOPY_GOLD_MISSION_RESPONSE_PATH=abfss://curated@stcanopydev5dt.dfs.core.windows.net/test/mission_e2e/mission_response_weekly/
```

`build_weekly_summary.py`는 `CANOPY_CONFIRMED_TRIPS_PATH`, `CANOPY_GOLD_WEEKLY_USER_PATH`, `CANOPY_GOLD_WEEKLY_CAMPAIGN_PATH`를 사용한다.

`build_mission_profile.py`는 Weekly User Gold, Mission Profile Gold, Mission Response Gold와 Cosmos 관련 환경변수를 사용한다.

## 7. merge 전 최소 게이트

팀원이 Mission Bundle 계약을 이어서 개발해야 한다면 전체 Mission Progress/Response E2E가 끝날 때까지 merge를 막을 필요는 없다. 다만 다음 최소 실환경 게이트는 먼저 통과한다.

1. 최신 PR head CI PASS
2. `mission-state` `/pk` 생성
3. Function Managed Identity가 `mission-state`를 read/create할 수 있음
4. branch build를 `func-canopy-dev` 전체 deployment unit으로 배포
5. cold-start GET 성공, policy version `mission-policy-v3.2`
6. 같은 user/week 재호출 시 동일 bundle id
7. deterministic Weekly Gold test PASS
8. Mission Profile ADLS write PASS
9. Mission Profile Cosmos latest projection PASS

이 9개가 PASS하면 PR #28은 core Mission Profile/API 계약 관점에서 merge 가능하다. Progress/Response 및 다음 주 학습 E2E는 후속 통합 게이트로 계속 검증한다.

## 8. merge 전 주의

`func-canopy-dev`는 app-level deployment unit이다. Mission 파일 하나만 배포하지 말고 `cloud/azure/functions/func_canopy_dev` 전체를 배포해야 기존 Functions가 사라지지 않는다.

현재 Mission endpoint는 `FUNCTION` auth이므로 통합 검증에는 Function key가 필요하다. 이 구조는 dev 검증에는 안전하지만, 실제 모바일/웹 클라이언트가 직접 호출하는 최종 서비스 인증 구조는 Easy Auth/APIM 등과 함께 별도 확정해야 한다. Function key를 모바일/웹 앱에 하드코딩하지 않는다.

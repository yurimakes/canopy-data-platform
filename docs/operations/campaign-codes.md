# 캠페인 가입 코드 운영

현재 허용 코드는 MSDS 하나다. 소문자 입력과 앞뒤 공백은 서버에서 정리한다. TEST/CANOPYTEST/미등록 코드는 거절한다. 기존 계정 로그인은 유지한다.

## 현재 승인 목록

`config/campaigns.main.json`이 관리 파일이며 메인 Function App의 `CANOPY_CAMPAIGNS_JSON`에 반영한다. 현재 구현은 **서버 설정 기반 허용 목록**이다. Cosmos의 캠페인 마스터를 읽는 구조나 관리자 화면을 새로 만든 것은 아니다.

```json
{
  "MSDS": {
    "campaign_id": "pipeline_test_iphone",
    "accepting_signups": true
  }
}
```

`pipeline_test_iphone`은 기존 데이터의 내부 식별자다. MSDS 코드를 기존 소속에 연결하여 기존 사용자·여정·보상·주간 집계의 연결을 유지한다. 코드와 내부 ID는 서로 다르다. 이번 변경으로 테스트 기록을 삭제하거나 다른 캠페인으로 이관하지 않았다. 새 운영 모집단을 완전히 분리하려면 별도 내부 ID를 만들고 해당 캠페인의 분석 입력·기준 데이터까지 검증한다.

## 추가 및 중지

1. `config/campaigns.main.json`을 수정한다. 코드는 대문자 1~20자로 정한다. 같은 campaign_id에 코드를 추가하면 같은 캠페인의 가입 경로가 늘어난다. 독립 집계가 필요한 새 캠페인에는 별도 campaign_id를 사용한다.
2. 예를 들어 `COMPANY2026` 키 아래 `campaign_id: company_2026`, `accepting_signups: true`를 추가한다. 기존 MSDS 항목도 유지해야 한다. 설정 적용은 목록 전체 교체다.
3. 필요하면 `signup_starts_at`, `signup_ends_at`을 시간대가 포함된 ISO 시각으로 설정한다. 종료 시각은 미포함이다. 즉시 신규 가입을 중지하려면 `accepting_signups`를 false로 변경한다. 기존 회원 로그인이나 기록을 삭제하는 기능은 아니다.
4. 프로젝트 루트에서 아래 명령으로 확인한 다음 적용한다.

```powershell
.venv/Scripts/python.exe tools/azure/set_campaign_codes.py
.venv/Scripts/python.exe tools/azure/set_campaign_codes.py --apply
```

대상은 메인 구독의 `5dt-2nd-team1 / func-canopy-dev`로 고정돼 있다. 다른 환경에 쓰려면 대상 구독·리소스를 별도로 검토한다. 스크립트는 허용 목록 설정만 갱신하고 다른 설정이나 Databricks를 변경하지 않는다. 적용 전 목록은 `.local-data/campaign-config/before.json`에 보관한다. Function 설정 변경 시 프로세스가 재시작될 수 있으므로 사용량이 적은 시간에 반영한다.

5. 적용 후 허용 코드 가입, 미등록·종료 코드 거절, 기존 로그인 유지 여부를 확인한다. 새로운 내부 ID라면 여정의 campaign_id, 캠페인별 보상·미션·Weekly·랭킹·KPI까지 검증한 뒤 모집한다. 승인되지 않은 이름을 사용자가 임의로 입력해 캠페인을 만드는 기능은 없다.

운영 환경에서 목록이 누락되면 신규 가입을 거절한다. 로컬 개발 환경에서만 기존 TEST 기본값을 허용한다. 서버 목록 변경 자체에는 앱 재빌드가 필요 없다. 기존 TestFlight 0.1.0(2)의 입력 예시 TEST는 구버전 안내이며 실제 입력에는 MSDS를 사용한다. 앱 소스의 입력 예시도 MSDS로 수정했으며 다음 빌드부터 반영된다.

## 적용 검증 — 2026-09-21

메인 API에 적용했다. 로컬 계정/허용 목록 테스트 14개와 하위 검사 4개 통과. 실제 API는 TEST/CANOPYTEST/UNKNOWN 요청에 400 invalid_campaign을 반환했다. MSDS 및 공백·소문자 입력은 캠페인 검증을 통과한 뒤 기존 이메일의 중복 계정 검사에서 409 account_exists를 반환했다. 검증을 위해 불필요한 계정은 생성하지 않았다. 기존 계정 로그인 200도 확인했다. Databricks 리소스는 변경하거나 시작하지 않았다.

## 가입 첫 화면 검증 보완

기존 빌드 2는 첫 화면에서 코드의 빈 값만 검사하고, 장소 입력 뒤 최종 가입 시 서버 검증을 수행했다. 빌드 3부터는 첫 화면의 다음 버튼에서 `/api/auth/campaign`을 호출하고 명시적 승인 응답을 받아야 장소 단계로 이동한다. 통신 오류나 거절 응답은 이동을 막는다. 최종 가입에서도 다시 검증하므로 중간에 가입이 중지된 캠페인은 가입할 수 없다.

메인 API의 TEST/FAKE/빈 값 400, MSDS 및 소문자·공백 입력 200을 확인했다. 서버 테스트 15개 및 하위 검사 4개, 앱 계정 테스트 8개와 타입 검사 통과. 빌드 3 ID: af81a978-84db-4d92-a24d-75f0a0132c20. 설치한 빌드 2의 첫 화면 동작은 서버 변경만으로 바뀌지 않으며 TestFlight 업데이트가 필요하다.

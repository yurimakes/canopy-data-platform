# CANOPY Admin Demo

관리자/기업용 정적 데모 웹입니다.

현재 구현 범위
- Power BI pipeline_test_iphone / 2026-W39 화면에서 확인 가능한 KPI 표시
- Dataset Explorer: campaign_kpi, mission_catalog, company_option_selections
- 관리자 / 기업 역할 전환
- 기업별 mission template 선택 및 브라우저 저장
- 관리자 선택 현황 조회
- CSV export
- 반응형 웹

데이터 상태
- campaign_kpi: 제공된 Power BI 화면에서 직접 확인 가능한 값만 사용
- mission_catalog: main의 mission-policy-v3.2 active catalog 기준
- company_option_selections: browser localStorage 데모 저장

주의
현재 mission-policy-v3.2에는 system_assigns_missions: true가 명시되어 있습니다. 이 웹의 기업 선택 UI는 데모 기능이며 실제 mission assignment pipeline에는 연결되지 않았습니다.

실제 운영 연결 전 필요 항목
1. 기업 선택이 mission catalog에 어떤 영향을 주는지 정책 확정
2. 저장 contract/schema 확정
3. 기존 CANOPY Azure 리소스 중 저장 위치 확정
4. func-canopy-dev 내부 API 추가
5. 권한/auth 확정
6. E2E 검증

로컬 실행
apps/admin-web 디렉터리에서 python -m http.server 4173 실행 후 http://localhost:4173 접속

Vercel 배포
Root Directory를 apps/admin-web 로 지정하고 정적 사이트로 배포합니다.

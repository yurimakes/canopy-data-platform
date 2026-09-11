# 기여 가이드

## 저장소 경계

- `apps/` — 배포 가능한 애플리케이션
- `ml/` — ML 모델, 추론, 평가, 공통 ML 컴포넌트
- `cloud/` — 클라우드별 인프라 및 배포 정의
- `data/` — 로컬 데이터 구조 및 소규모 fixture. 대용량 데이터는 원칙적으로 커밋하지 않음
- `shared/` — 컴포넌트 간 공통 스키마, 설정, 상수
- `tools/` — 개발 및 운영 보조 도구
- `tests/` — 컴포넌트 간 통합 테스트 및 E2E 테스트
- `docs/` — 아키텍처 및 프로젝트 문서
- `legacy/` — 이전 또는 미이관 구현. 신규 개발 금지

## 브랜치 및 PR

- `main`은 공유 기준 브랜치입니다. 일반 작업은 `main`에 직접 push하지 않고 작업 브랜치에서 진행한 뒤 PR로 병합합니다.
- 브랜치 이름은 작업 목적이 드러나도록 `feature/`, `fix/`, `chore/`, `docs/` 등의 prefix 사용을 권장합니다.
- 짧고 단순한 변경은 별도 승인 없이 병합할 수 있으며, 영향이 크거나 판단이 필요한 변경은 팀원 리뷰를 권장합니다.
- force push와 `main` 브랜치 삭제는 하지 않습니다.
- 병합이 끝난 작업 브랜치는 필요하지 않다면 삭제합니다.

## 규칙

1. 팀 합의 없이 새로운 최상위 디렉터리를 만들지 않습니다.
2. ML 모델 디렉터리는 `ml/models/` 아래에서 예측 과제 단위로 구성합니다.
3. ML 내부에서만 재사용하는 코드는 `ml/shared/`, 시스템 간 공통 계약은 루트 `shared/`에 둡니다.
4. 배포 대상 코드는 `tools/`에 두지 않습니다.
5. 애플리케이션 코드는 가능한 한 Azure 구현과 분리하고, Azure 전용 배포 정의는 `cloud/azure/`에 둡니다.
6. 대용량 데이터셋, 학습된 모델 바이너리, 캐시, 생성된 빌드 산출물은 명시적 합의 없이 커밋하지 않습니다.
7. 실제 `.env`, `.env.local`, `*.secret.env`, `Local.xcconfig`는 기본적으로 커밋하지 않습니다.
8. 예외적으로 `.env.shared`에는 프로젝트 기간에만 유효하고 권한이 제한된 단기 credential을 둘 수 있습니다. 이 경우 저장소는 private이어야 하며 프로젝트 종료 시 반드시 revoke/rotate 합니다.
9. Python dependency는 해당 runtime이 소유합니다. API dependency는 `apps/api/requirements.txt`, ML dependency는 `ml/requirements.txt`에서 관리하고, 독립 Azure Function은 해당 Function 디렉터리에서 별도 `requirements.txt`를 둡니다.
10. 여러 runtime의 dependency를 루트 `requirements.txt` 하나로 합치지 않습니다.
11. 기존 구현을 `legacy/`로 이동하거나 `legacy/`에서 꺼낼 때는 해당 코드의 상태와 새 소유 위치가 명확해야 합니다.

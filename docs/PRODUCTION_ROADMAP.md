# Production 전환 로드맵

## 1. 상태와 사용법

현재 저장소에는 Go 기반 API/controller/내부 model proxy/CLI, AgentSession v1alpha1, 통합 terminal gateway, OpenCode 기본 runtime 및 kind/Helm 개발 경로가 있다. 초기 설계의 모든 선택 사항이 구현되었다는 뜻은 아니다. 현재 CI와 kind는 전체 Production 보장을 제공하지 않는다.

이 문서는 후속 작업의 순서·의존성·종료 증거를 소유한다. [요구사항](PRODUCTION_REQUIREMENTS.md)은 목표를, [출시 기준](RELEASE_CRITERIA.md)은 판정을, [초기 구현 계획](IMPLEMENTATION_PLAN.md)은 초기 단계 이력을 설명한다. 아래 항목은 출시 증거가 아직 확보되지 않은 계획이며 구현 완료 체크리스트가 아니다. 날짜/인력/성능 수치를 근거 없이 약속하지 않는다.

## 2. 위험과 의존성에 따른 단계

| 단계 | 후속 작업 | 의존성 및 종료 증거 | 상태 |
| --- | --- | --- | --- |
| A. 기준과 현황 | 현재 코드/배포의 지원 기능·계약·위협 모델 inventory, 사용자 시나리오 및 운영 SLO/성능·자원 목표 정의 | 담당자·환경·수치·근거를 갖춘 release evidence 초안, 현재/목표 gap 목록 | 정책 문서 외 실제 출시 증거 미확보 |
| B. 보안·계약 | 실제 신원 체계, 사용자/세션 인가·철회, 최소 RBAC, Secret 회전/누출 방지, 데이터/자원/네트워크/실행 격리, API/CRD 호환성 정책 | A의 위협 모델; 실제 환경 권한 부정·누출·격리 및 호환성 테스트 | Production 검증 필요 |
| C. 복구·운영·확장 | 장애/재시작/cleanup, 필요 시 영속화·백업/복원, 관측성·경보·운영 가이드, 재현 배포/업그레이드·롤백, 목표 부하·용량·HA 검증 | A의 SLO/예산과 B의 경계; 장애 주입·복구/부하 실측 및 운영 대응 결과 | Production 검증 필요 |
| D. 요구사항별 제품 확장 | Web UI/관리 포털, 조직·세분화 권한·quota/billing, 복수 runtime, 고급 gateway, 고급 session/workspace, 동적 정책 | 검증된 요구와 개별 ADR; 실제 사용자·provider/runtime 흐름 및 해당 출시 기준 | 도입 여부·우선순위 미확정 |

단계는 고정 워터폴이 아니다. 예를 들어 신원 통합이나 자원 통제에 필요한 조직/정책 기능은 B에서, 목표 SLO에 필요한 HA는 C에서 필수 작업으로 당긴다. 다른 Agent Runtime을 OpenCode보다 영구 후순위로 두지 않는다.

## 3. 구조 변경 후보

독립 Terminal Gateway, provider별 gateway, 저장소, 중앙 인증/OIDC, 이벤트 기반 controller, 멀티테넌시 및 동적 격리 정책은 허용된 선택이다. 현재 Go/CRD 자산을 활용하고 각 변경의 필요·계약/보안·운영 비용·마이그레이션을 ADR로 결정한다. Vault/SPIFFE/External Secrets 같은 특정 기술이나 유료 Billing 자체가 모든 배포의 필수 조건은 아니다.

## 4. 완료 판단

각 작업은 요구사항/ADR/구현 PR/자동화/운영 문서/실제 환경 증거를 연결한다. Mock/Fake/Stub 및 kind만으로 완료하지 않는다. 미실행 항목·목표 미정·환경 제한은 미충족으로 기록하고 지원 범위를 제한한다. 전체 Production Ready 표시는 릴리스별 [Quality Gate](RELEASE_CRITERIA.md) 충족 후에만 가능하다.

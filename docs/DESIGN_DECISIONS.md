# Architecture Decisions / ADR

## 관리 원칙

이 문서는 기존 초기 설계 결정의 이력과 앞으로의 ADR을 함께 관리한다. 별도 중복 ADR 인덱스는 만들지 않는다. 현재 배포 형태는 구현 기준선이지 영구 제품 제한이 아니다. Go 핵심 서비스와 AgentSession CRD를 유지하면서 [Production 요구사항](PRODUCTION_REQUIREMENTS.md)을 충족하도록 발전시킨다.

## 결정 목록

| ID | 결정 | 상태 | 현재 의미 |
| --- | --- | --- | --- |
| ADR-001 | CLI-first, no portal | 대체됨: ADR-006 | 초기 개발 속도와 단순 UX를 위한 MVP 결정이었다. CLI-only 또는 Web UI 금지는 더 이상 유효하지 않다. 현재 UI가 없는 구현 상태만 남는다. |
| ADR-002 | API와 Terminal Gateway 결합 | 범위 제한 대체됨: ADR-006 | 초기 구성 요소 수와 로컬 테스트 단순화를 위한 결정이었다. 현재 결합 구현은 유지하되 영구 결합 의무는 없다. |
| ADR-003 | Agent Pod 비공개 | 유지 | 기본 세션별 Ingress/public Service를 만들지 않고 인증·인가된 제품 gateway를 사용한다. 사용자는 Kubernetes/Pod에 직접 접근하지 않는다. |
| ADR-004 | isolationProfiles 추상화 | 유지·확장 가능 | 사용자에게 raw runtimeClassName을 노출하지 않는다. controller가 검증된 profile을 runtime/node 설정에 매핑한다. |
| ADR-005 | 내부 model proxy 자격 증명 경계 | 유지·기능 확장 가능 | 실제 upstream 키는 내부 cask-model-proxy만 보유한다. Agent Pod/CR/사용자 출력에 키를 전달하지 않는다. 최소 proxy 기능만 유지한다는 제한은 없다. |
| ADR-006 | 정식 제품 개발 정책 | 채택: 2026-10-25 | MVP 기능 상한을 해제하고 Production Quality Gate를 적용한다. 이 결정만으로 제품 준비 완료를 선언하지 않는다. |

## ADR-006: 정식 제품 개발 정책

**배경:** 초기 MVP의 범위 축소가 장기 제품 개발을 금지하는 규칙으로 읽힐 수 있었다. 기능 범위와 보안 경계를 구분해야 한다.

**결정:** Web UI/관리 포털, 독립 Terminal Gateway, provider/모델 gateway, 데이터 저장소, OIDC/보안 통합, 이벤트 기반 controller, 동적 정책, 세션·워크스페이스 영속화/복구, 복수 런타임, 멀티테넌시·조직·quota/billing 및 필요한 HA/수평 확장을 허용한다. 요구와 위험에 맞춰 선택하며 이번 변경에서 구현하지 않는다. OpenCode와 CLI는 현재 기본 선택일 뿐 영구 우선순위가 아니다.

**보존:** upstream 키 비노출, 사용자·세션 인증/인가, 비신뢰 실행 격리, 최소 RBAC, 자원·데이터 분리와 비공개 네트워크. 보안 기술을 도입할 자유가 보안 경계의 면제를 뜻하지 않는다.

**영향:** 현재 실행 코드, API 경로, CRD v1alpha1, 배포 설정 및 kind 클러스터 식별자는 변경하지 않는다. 향후 구조/계약 변경은 개별 ADR로 평가한다. 최소 구현과 Mock/kind 성공을 전체 완료 기준으로 삼지 않고 [Release Criteria](RELEASE_CRITERIA.md)를 적용한다. [로드맵](PRODUCTION_ROADMAP.md)이 후속 작업을 구분한다.

**대안:** MVP 제한 유지(제품 확장 차단), 모든 선택 기능 즉시 구현(요구 없는 복잡성 증가)을 채택하지 않는다.

## 신규 ADR 양식

```text
ID / 제목 / 날짜 / 상태(proposed, accepted, superseded, rejected):
대체하거나 영향을 받는 결정:
사용자 요구·문제·측정 근거:
대안과 기술적 선택 이유:
현재 구현과 목표 구조의 차이:
인증/인가·신뢰/Secret·네트워크·데이터 격리 경계:
운영 비용·관측성·용량/HA·장애/복구 영향:
API/CRD/클라이언트 호환성 및 마이그레이션/롤백:
단계적 도입·검증/출시 증거·책임자:
잔여 위험 및 결정 검토자:
```

상태와 대체 관계를 명시하고 과거 이유는 이력으로 보존한다. 구현 속도만으로 확장성/안정성을 희생하지 않으며, 실제 요구나 운영 위험 없이 서비스를 분리하거나 추상화를 추가하지 않는다.

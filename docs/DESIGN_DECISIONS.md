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
| ADR-007 | JWT 검증 및 세션 소유권 경계 | 채택: 2026-10-25 | 임의 개발 Bearer를 제거한다. P0-1a 구현이며 CLI login/refresh·철회·조직 RBAC와 실제 IdP 검증은 잔여 작업이다. |

## ADR-006: 정식 제품 개발 정책

**배경:** 초기 MVP의 범위 축소가 장기 제품 개발을 금지하는 규칙으로 읽힐 수 있었다. 기능 범위와 보안 경계를 구분해야 한다.

**결정:** Web UI/관리 포털, 독립 Terminal Gateway, provider/모델 gateway, 데이터 저장소, OIDC/보안 통합, 이벤트 기반 controller, 동적 정책, 세션·워크스페이스 영속화/복구, 복수 런타임, 멀티테넌시·조직·quota/billing 및 필요한 HA/수평 확장을 허용한다. 요구와 위험에 맞춰 선택하며 이번 변경에서 구현하지 않는다. OpenCode와 CLI는 현재 기본 선택일 뿐 영구 우선순위가 아니다.

**보존:** upstream 키 비노출, 사용자·세션 인증/인가, 비신뢰 실행 격리, 최소 RBAC, 자원·데이터 분리와 비공개 네트워크. 보안 기술을 도입할 자유가 보안 경계의 면제를 뜻하지 않는다.

**영향:** 현재 실행 코드, API 경로, CRD v1alpha1, 배포 설정 및 kind 클러스터 식별자는 변경하지 않는다. 향후 구조/계약 변경은 개별 ADR로 평가한다. 최소 구현과 Mock/kind 성공을 전체 완료 기준으로 삼지 않고 [Release Criteria](RELEASE_CRITERIA.md)를 적용한다. [로드맵](PRODUCTION_ROADMAP.md)이 후속 작업을 구분한다.

**대안:** MVP 제한 유지(제품 확장 차단), 모든 선택 기능 즉시 구현(요구 없는 복잡성 증가)을 채택하지 않는다.

## ADR-007: JWT 검증 및 세션 소유권 경계

**문제/위협:** 임의 Bearer가 dev-user, `user:xxx`가 임의 사용자로 처리되어 기존 owner 비교를 우회했다. 요청 본문·email·사용자 이름은 신뢰 가능한 소유권 키가 아니다.

**선택:** Go 핵심 구조와 CRD를 유지하고 `internal/auth`에 coreos/go-oidc v3 검증기를 둔다. 서버가 명시적으로 설정한 HTTPS issuer/audience/JWKS만 신뢰한다(redirect 금지, TLS 검증, 5초 HTTP timeout). RS256/ES256 allowlist, 서명/issuer/audience/exp/sub/nbf를 검증하고 API 전용 audience 및 `cask:sessions` scope를 요구한다. opaque token/ID token 직접 사용/사용자 지정 jku 및 개발 토큰을 지원하지 않는다. discovery는 생략하고 운영자가 JWKS URL을 고정한다. 인증 실패 401, 유효 identity의 scope/소유권 부족 403. scope claim이 없는 JWT는 세션 권한을 갖지 않는다.

**Identity/정책:** 정확한 `[issuer,subject]` JSON 배열의 SHA-256을 padding 없는 소문자 base32로 인코딩하고 `u-` 접두사를 붙인다(54자, Kubernetes label 유효). email/username 변경이나 token 갱신에 소유권이 바뀌지 않는다. API는 모든 기존 세션 접근을 owner로 제한하고 목록도 재필터링한다. 추가 정책 인터페이스는 owner 권한을 더 제한할 수 있지만 공유/이전 권한을 부여하지 못한다. 조직/프로젝트 모델은 별도 ADR/구현으로 추가한다.

**Terminal:** upgrade 전 재인증/owner 인가 및 gateway 재검증. JWT 만료에 request context deadline을 걸고 연결/exec를 종료한다. 연결 중 owner/세션 상태/TTL은 2초마다 재확인하며 오류에도 닫는다. 기본 Origin은 같은 host 또는 Origin 없는 CLI만 허용한다. terminal 전체 heartbeat/frame/backpressure/UID 검증은 별도 P1-3/P0-5 단위다.

**운영:** JSON 감사 이벤트에는 해시 owner/action/세션 ID/결과만 포함하고 JWT·원시 claims·provider 오류는 기록하지 않는다. 검증 실패 상세를 응답/로그에 노출하지 않는다. JWKS는 캐시/새 키 재조회되며 미확인 키+IdP 장애는 거부한다. 이미 캐시된 유효 키는 장애 중에도 검증 가능하며 키 제거는 즉시 철회가 아니다. `/readyz`는 local auth 구성과 Kubernetes 접근만 확인하며 IdP 가용성 보장은 아니다. 실제 IdP의 짧은 access-token TTL/비상 API 중단·재시작 절차와 후속 introspection/denylist가 필요하다.

**대안:** 자체 JWT 암호 구현(불필요한 위험), 임의 문자열 개발 모드 유지(우회 위험), 외부 인증 proxy의 신뢰되지 않은 header 사용(신원 위조)을 제외했다. JWKS fetch storm/정책 캐시·분산 revoke·감사 수집/보존/metrics는 후속 운영 작업이다.

**호환성/마이그레이션:** API 경로/CRD group/version/schema는 유지하지만 인증 계약은 의도적으로 breaking이다. `dev-user`/`alice` 등 레거시 owner와 새 해시는 자동 연결하지 않는다. 배포 전 활성 세션을 drain/delete하고 JWT로 재생성하는 것이 기본이다. 보존이 필요하면 관리자가 IdP의 검증된 issuer/sub를 대조한 별도 승인 migration으로 spec과 label을 함께 변경해야 한다(도구 미제공). 임의 username 매칭·dev fallback으로 접근을 복원하지 않는다. rollback으로 취약 인증을 복구하지 말고 접근을 차단한 채 forward fix한다.

**출시 범위/비용:** 모든 환경에서 issuer/audience/JWKS가 필수다. Helm 기본 렌더는 누락 시 실패하고 render-only CI fixture는 로그인 가능한 구성이 아니다. CLI는 외부에서 발급한 JWT를 전달하며 device login/refresh/안전한 저장은 P0-1b다. 테스트의 로컬 TLS JWKS는 실제 IdP가 아니므로 이번 단위로 Production 인증 전체를 완료하지 않는다.

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

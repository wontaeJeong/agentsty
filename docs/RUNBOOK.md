# Runbook: agentcask Baseline

These are existing operator diagnostics for the current topology, not a complete production operations guide. Kubernetes commands are for authorized operators with least-privilege access, not end-user product access. Never copy secrets or unredacted terminal/model bodies into diagnostic output or incident reports.

## 1. Check system pods

```bash
kubectl -n agentcask-system get pods
```

Expected:

```text
cask-api
cask-model-proxy
cask-controller
```

## 2. Check CRD

```bash
kubectl get crd agentsessions.agentcask.aidev.samsungds.net
```

## 3. List sessions

```bash
kubectl -n agentcask-sessions get agentsessions
```

## 4. Inspect a failed session

```bash
kubectl -n agentcask-sessions get agentsession <name> -o yaml
```

Check:

```text
status.phase
status.reason
status.message
```

## 5. Common failures

### RuntimeClassNotFound

Cause:

```text
isolation.profile maps to a RuntimeClass that does not exist
```

Fix:

```bash
kubectl get runtimeclass
```

Install the runtime or change `isolationProfiles`.

### PodUnschedulable

Cause:

```text
nodeSelector/tolerations do not match available nodes
```

Fix:

```bash
kubectl describe pod <pod>
kubectl get nodes --show-labels
```

### TerminalNotReady

Cause:

```text
Pod not ready, container missing, or pods/exec permission missing
```

Fix:

```bash
kubectl auth can-i create pods/exec --as system:serviceaccount:agentcask-system:cask-api -n agentcask-sessions
```

### SecretLeakTestFailed

Cause:

```text
fake upstream key appeared in Pod/CR/API/log output
```

Fix:

- remove real/sentinel key from Agent Pod env
- ensure only proxy token is injected
- update redaction middleware

### ModelProxyUnauthorized

Cause:

```text
session proxy token is expired, revoked, invalid, or no longer maps to a live AgentSession
```

Fix:

```bash
kubectl -n agentcask-system logs deploy/cask-model-proxy
kubectl -n agentcask-sessions get agentsession <name> -o yaml
```

## 6. Force cleanup

```bash
kubectl -n agentcask-sessions delete agentsession <name>
```

If finalizer is stuck during development only:

```bash
kubectl -n agentcask-sessions patch agentsession <name> \
  --type=json \
  -p='[{"op":"remove","path":"/metadata/finalizers"}]'
```

Use finalizer removal only for dev/test recovery.

## 7. Production operations gaps and release prerequisites

Before production use, supply and exercise deployment-specific procedures for identity/permission incidents, key/token rotation and revocation, dependency outages, node/component failure, cleanup failures, storage retention and backup/restore where state is persistent, upgrade/migration/rollback, alert response and capacity/performance management. Define recovery-time/data-loss objectives and demonstrate recovery against them.

These procedures and guarantees are not implemented by this runbook update. Record operator ownership, safe diagnostics, monitoring signals, exact supported configuration and drill evidence in the release record. Do not remove finalizers in production without a reviewed recovery procedure that checks resource/data cleanup and ownership. See [Release Criteria](RELEASE_CRITERIA.md) and [Production Roadmap](PRODUCTION_ROADMAP.md).

## 8. JWT 인증 운영 (P0-1a)

### 구성 및 배포 전제

- API 실행 전 `CASK_OIDC_ISSUER`, `CASK_OIDC_AUDIENCE`, `CASK_OIDC_JWKS_URL`이 필수다. issuer/JWKS는 인증서가 검증되는 HTTPS URL이며 HTTP·userinfo·query·fragment는 허용하지 않는다. 공인 CA 기준이며 별도 CA는 이미지/플랫폼 trust store에 설치한다(TLS 검증을 끄지 않는다).
- IdP가 API 전용 audience, 안정적인 `sub`, 짧은 `exp`, 정확한 `cask:sessions` scope를 갖는 RS256/ES256 JWT **access token**을 발급하도록 구성한다. OAuth client ID와 API audience를 혼동하지 않는다. opaque access token이나 로그인용 ID token을 대신 사용하지 않는다.
- Helm `api.oidc.{issuer,audience,jwksURL}`는 필수다. kind의 `make kind-deploy`는 위 환경 변수에서 `cask-api-auth` ConfigMap을 만든다. 이는 공개 인증 메타데이터이며 JWT를 저장하지 않는다.
- 신규 설정은 Pod rollout/restart 시 적용된다. 인증만 강화된 상태로 다른 P0가 해결되었다고 판단하지 않는다.

### 실패 진단과 키 회전

1. 시작 실패 시 필수 설정 누락/HTTPS URL 형식을 확인한다. 기존 dev-token 또는 `--memory`로 우회하지 않는다.
2. 401은 미검증 credential이다. 토큰 내용을 로그/issue에 복사하지 말고 승인된 IdP 도구로 issuer/audience/서명 알고리즘/exp/nbf/sub와 시스템 시계를 확인한다.
3. 403은 scope 또는 owner 정책이다. `scope`에는 정확히 `cask:sessions`가 공백 구분 항목으로 포함되어야 한다. 이메일/사용자 이름으로 owner를 덮어쓰지 않는다.
4. JSON `authentication.failed/succeeded`, `authorization.denied/allowed` 이벤트를 수집한다. 기본 출력은 stderr다. 인증 실패는 공격자 입력을 로그에 남기지 않는다. 감사 수집기/접근 제한/보존 및 경보 정책은 배포별로 별도 구성하고 아직 미검증이다.
5. JWKS 새 키는 새 JWT의 검증 실패 시 재조회한다. 새 public key를 먼저 게시하고, 새 키 발급 후 기존 access-token TTL만큼 겹친 뒤 기존 키를 제거한다. 통제된 환경에서 정상 토큰/새 키/미확인 키/잘못된 서명/IdP outage를 검증한다.
6. JWKS 요청은 redirect 금지/5초 timeout이다. DNS/egress/TLS 신뢰 문제면 미확인 키 인증이 거부된다. 캐시된 키로 이미 검증 가능한 토큰은 IdP outage 중에도 exp까지 허용된다. `/readyz`는 IdP 상태를 검사하지 않으므로 인증 실패율은 별도로 감시해야 한다.

### 만료·철회·비상 대응

- 새 요청은 exp에 401로 거부한다. 이미 열린 터미널도 JWT 만료 시 닫는다. 세션 삭제/owner 변경/TTL/상태 오류는 최대 2초 polling으로 연결을 닫는다. 네트워크/exec 문제의 세부 hardening은 P1-3 미완료다.
- logout/IdP revoke/기존 JWKS key 제거의 **즉시 철회는 제공하지 않는다**. token denylist/introspection은 후속 구현이다. JWT 탈취 시 먼저 외부 API/terminal 진입을 차단하고 활성 연결을 종료하기 위해 API Deployment를 정지한다(서비스 중단을 수반하므로 승인된 incident 절차로 수행). IdP 토큰 발급/키·TTL 정책을 수정하고 모든 손상된 토큰의 exp가 지난 후 새 Pod로 재개한다. 단순 재시작이나 JWKS에서 key 삭제만으로 공격자 토큰이 즉시 무효화된다고 가정하지 않는다.
- 이전 `dev-user`/임의 username owner 세션은 새 identity와 자동 연결하지 않는다. rollout 전 drain/delete 후 JWT로 재생성한다. 보존이 필요하면 승인된 issuer/sub 대조 migration으로 spec.userId와 owner label을 함께 변경해야 하며 자동 도구는 제공하지 않는다. 취약 개발 인증으로 rollback하지 않는다.

### 실제 cluster/IdP 검증 재현

격리된 테스트 cluster에서 위 IdP 설정 및 해당 IdP가 발급한 짧은 JWT `CASK_E2E_TOKEN`을 공급한 뒤 `make kind-test`를 실행한다. 다른 사용 중인 cluster를 가리키지 않도록 별도 KUBECONFIG/context를 확인한다. 값이 없으면 preflight가 실패하며 E2E 성공으로 집계하지 않는다. 기존 E2E는 stub 터미널/가짜 repo/최소 proxy 경로 검증이므로 실제 checkout/agent/provider/격리는 별도의 P0-3/4/5/6 증거가 필요하다.

로컬 `go test ./internal/auth ./internal/api`는 TLS JWKS fixture의 정상/변조/만료/issuer/audience/sub/nbf/scope/rotation/concurrency/outage와 owner 경계를 확인한다. fixture는 실제 IdP가 아니며 CLI login/refresh 및 IdP 설정의 적합성을 증명하지 못한다.

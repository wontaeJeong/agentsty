# agentcask

`agentcask`는 격리된 대화형 Agent 세션을 Kubernetes 위에서 실행하는 플랫폼으로, 정식 Production 서비스를 목표로 개발합니다. 현재 구현 기준선은 `cask-api`, 내부 전용 `cask-model-proxy`, `cask-controller`, `caskctl`, `AgentSession` CRD, WebSocket 터미널 게이트웨이입니다. 이 정책 전환이 현재 구현의 Production Ready 인증을 뜻하지는 않습니다.

`opencode`가 현재 기본 Agent 도구입니다. `caskctl session create`는 기본적으로 `--tool opencode`를 사용하며, Agent Pod는 공개 이미지 `ghcr.io/anomalyco/opencode:1.14.48`에 Git·SSH·tmux와 테스트 어댑터를 추가한 `agentcask/agent-runtime:dev`를 기본으로 사용합니다. 터미널 경로를 결정적으로 테스트할 때는 `stub` 도구를 사용할 수 있지만 실제 모델 연동 성공의 증거는 아닙니다. 다른 Agent Runtime 지원을 영구 후순위로 두지 않습니다.

## 개발 정책과 Production 기준

- [Production 요구사항](docs/PRODUCTION_REQUIREMENTS.md): 모든 기능의 필수 품질·보안 역량과 요구에 따른 선택 기능.
- [Production 로드맵](docs/PRODUCTION_ROADMAP.md): 현재 상태, 후속 작업, 의존성과 미확보 증거.
- [Production 구현 백로그](docs/PRODUCTION_BACKLOG.md): 최신 코드에서 재확인한 P0/P1/P2 결함과 독립 구현 단위.
- [Production Quality Gate](docs/RELEASE_CRITERIA.md): 실제 사용자 시나리오, 인증·인가, 복구, 다중 사용자/세션, 관측성, 계약·배포, 문서, 성능·자원 기준.
- [설계 결정/ADR](docs/DESIGN_DECISIONS.md): 초기 결정 이력과 구조 변경 근거·호환성 관리.

Web UI/관리 포털, 독립 Terminal Gateway, 고급 모델 gateway, 영속화, 조직·quota/billing, HA·수평 확장 및 복수 런타임을 요구사항에 따라 도입할 수 있습니다. API의 JWT/JWKS 검증과 세션 소유권 경계가 구현되어 있으나 CLI device login/refresh·즉시 철회 및 나머지 P0는 미완료입니다. Mock/Fake/Stub 또는 kind 성공만으로 서비스 전체를 완료 처리하지 않습니다.

## 빠른 검증

```bash
make test
# 아래 IdP 설정과 CASK_E2E_TOKEN을 준비한 후 실행
make kind-test
```

`make kind-test`는 `agentcask-mvp` kind 클러스터를 생성/사용하고, `cask-api`, `cask-model-proxy`, `cask-controller`, 파생 Agent 런타임 로컬 이미지를 빌드 및 로드한 뒤 CRD/RBAC/Deployment를 설치합니다. 이후 `caskctl`로 세션 생성, 터미널 연결, 삭제 흐름을 실행하고, 분리된 모델 프록시를 검증하며, `REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK` 센티널 키가 AgentSession YAML, Agent Pod env, API/CLI 출력, 터미널 출력, 컴포넌트 로그에 노출되지 않는지 확인합니다. E2E 포트 포워딩은 빈 로컬 포트를 자동 선택하므로 기존 SSH 터널과 충돌하지 않습니다.

## 사용자가 직접 테스트하는 방법

### 1. 준비물

- Go 1.25+
- Docker
- kind
- kubectl
- 선택: Helm, Helm 차트 설치 경로를 테스트할 때만 필요

현재 구현에는 Web UI가 없으며 제공된 사용자 클라이언트는 `caskctl`입니다. 이는 UI 개발 금지가 아닙니다. `caskctl`은 Kubernetes API가 아니라 `cask-api`에만 접속합니다. 로컬 이미지·포트 포워딩은 개발 검증용이며 Production 배포 구성이 아닙니다. **dev-token/user:xxx는 더 이상 허용하지 않습니다.**

모든 API 실행 모드에 검증된 JWT가 필요합니다. HTTPS 테스트 IdP에 API audience와 `cask:sessions` scope를 구성하고 다음 값을 공급하세요. 실제 토큰을 shell history/저장소/로그에 붙여 넣지 마세요. CLI 자체 login/refresh는 아직 제공되지 않습니다.

```bash
export CASK_OIDC_ISSUER=https://your-test-idp.example/issuer
export CASK_OIDC_AUDIENCE=cask-api
export CASK_OIDC_JWKS_URL=https://your-test-idp.example/issuer/keys
# 승인된 외부 인증 절차로 CASK_TOKEN을 공급하고, E2E 실행 시에만:
export CASK_E2E_TOKEN="$CASK_TOKEN"
```

예시 URL은 실제 IdP가 아닙니다. 실제 값/짧은 수명의 JWT로 교체해야 합니다. 키 회전·이전 세션 마이그레이션·검증 한계는 [Runbook](docs/RUNBOOK.md#8-jwt-인증-운영-p0-1a)을 참고하세요.

### 2. 로컬 바이너리 빌드

```bash
make build
```

빌드가 끝나면 다음 바이너리가 생성됩니다.

```text
bin/cask-api
bin/cask-controller
bin/cask-model-proxy
bin/caskctl
```

CLI가 실행되는지 먼저 확인합니다.

```bash
./bin/caskctl --help
```

예상 출력:

```text
Usage: caskctl session <create|list|get|connect|delete>
```

### 3. kind에 agentcask 배포

정적 kind 매니페스트로 배포하려면 다음을 실행합니다.

```bash
make kind-up
make kind-load
make kind-deploy
```

명령이 성공하면 `agentcask-system` 네임스페이스에서 다음 Deployment가 Ready 상태가 됩니다.

```bash
kubectl -n agentcask-system get deploy
```

확인 대상:

```text
cask-api
cask-model-proxy
cask-controller
```

Helm 차트를 테스트하고 싶다면 정적 매니페스트 대신 아래 경로를 사용합니다. 같은 네임스페이스에서 두 방식을 섞지 마세요.

```bash
make kind-up
make kind-load
helm upgrade --install agentcask ./charts/agentcask \
  --namespace agentcask-system \
  --create-namespace \
  --set-string api.oidc.issuer="$CASK_OIDC_ISSUER" \
  --set-string api.oidc.audience="$CASK_OIDC_AUDIENCE" \
  --set-string api.oidc.jwksURL="$CASK_OIDC_JWKS_URL"
kubectl -n agentcask-system rollout status deploy/cask-api --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-model-proxy --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-controller --timeout=180s
```

### 4. caskctl을 cask-api에 연결

터미널 하나에서 `cask-api`를 포트 포워딩합니다.

```bash
kubectl -n agentcask-system port-forward svc/cask-api 18080:8080
```

다른 터미널에서 `caskctl` 환경 변수를 설정합니다.

```bash
export CASK_API_SERVER=http://127.0.0.1:18080
# CASK_TOKEN은 앞서 승인된 외부 인증 절차로 공급한 JWT를 사용합니다.
```

### 5. 세션 생성, 조회, 터미널 접속, 삭제

터미널 게이트웨이를 안정적으로 확인하려면 `stub` 도구를 사용합니다. 이 경로는 실제 모델 호출에 의존하지 않습니다.

```bash
./bin/caskctl session create \
  --tool stub \
  --repo https://example.invalid/repo.git \
  --branch main \
  --model default \
  --resource small \
  --isolation default \
  --ttl 30m
```

예상 출력:

```text
ID: sess-...
Phase: Pending
```

출력된 세션 ID를 `SESSION_ID`로 저장합니다.

```bash
export SESSION_ID=<위에서 출력된 ID>
```

세션 목록과 상세 상태를 확인합니다.

```bash
./bin/caskctl session list
./bin/caskctl session get "$SESSION_ID"
```

`Phase`가 `Running`이고 `TerminalReady: true`가 되면 터미널에 접속합니다.

```bash
./bin/caskctl session connect "$SESSION_ID"
```

접속된 터미널 안에서 다음을 실행해 실제 입출력이 오가는지 확인합니다.

```bash
echo CASK_OK
exit
```

터미널에 `CASK_OK`가 출력되고 `exit` 후 로컬 셸로 돌아오면 터미널 게이트웨이까지 정상 동작한 것입니다.

테스트가 끝나면 세션을 삭제합니다.

```bash
./bin/caskctl session delete "$SESSION_ID"
```

삭제 후 목록에서 사라졌는지 확인합니다.

```bash
./bin/caskctl session list
```

### 6. opencode 기본 세션 테스트

사용자 관점의 기본 세션을 확인하려면 `--tool`을 생략하거나 `--tool opencode`를 사용합니다.

```bash
./bin/caskctl session create \
  --repo https://example.invalid/repo.git \
  --branch main \
  --model default \
  --resource small \
  --isolation default \
  --ttl 30m
```

`opencode`는 기본 도구이므로 위 명령은 다음과 같습니다.

```bash
./bin/caskctl session create --tool opencode ...
```

실제 모델/provider 동작은 배포 환경의 내부 `cask-model-proxy` 설정에 좌우됩니다. 터미널 연결 자체를 검증하려면 `stub`을 사용하세요.

### 7. 정리

로컬 kind 클러스터를 삭제하려면 다음을 실행합니다.

```bash
make kind-down
```

빌드 산출물을 지우려면 다음을 실행합니다.

```bash
make clean
```

## 참고 문서

- 수동 kind 테스트 상세 가이드: `docs/KIND_TESTING.md`
- API 스펙: `docs/API_SPEC.md`
- CLI 스펙: `docs/CLI_SPEC.md`
- 아키텍처: `docs/ARCHITECTURE.md`
- CI/CD: `docs/CI_CD.md`

## 현재 구현의 한계와 유지할 보안 경계

- Web UI는 구현되어 있지 않습니다.
- 현재 배포에서 외부로 노출되는 런타임 컴포넌트는 `cask-api`뿐입니다. 인증·인가와 보안 경계를 지키는 UI/gateway 확장은 ADR로 허용합니다.
- `cask-model-proxy`는 내부 전용이며 upstream 모델/API 키를 보관할 수 있는 유일한 컴포넌트입니다.
- Agent Pod에는 내부 `cask-model-proxy` URL, 짧은 수명의 세션 proxy token, projected service account token만 전달됩니다.
- 세션별 Ingress 또는 public Service는 기본 생성하지 않습니다.
- kind의 Kata isolation 테스트는 plumbing 검증용입니다. `isolation.profile=kata -> pod.spec.runtimeClassName=kata` 매핑만 확인하며 실제 Kata VM 격리를 검증하지 않습니다.
- 실제 다중 사용자/세션·provider 연동, 장애 복구, 부하·성능, 운영 및 격리 보장은 별도 Production 환경 증거가 필요합니다. `make test`의 opt-in E2E skip은 kind/runtime E2E 실행으로 세지 않습니다.
- `agentcask-mvp` 클러스터명은 기존 테스트와의 호환성을 위해 유지한 식별자이며 제품 범위 제한이 아닙니다.

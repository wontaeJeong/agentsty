# agentcask MVP

`agentcask`는 격리된 대화형 Agent 세션을 Kubernetes 위에서 실행하기 위한 CLI-first 플랫폼입니다. MVP는 `cask-api`, 내부 전용 `cask-model-proxy`, `cask-controller`, `caskctl`, `AgentSession` CRD, WebSocket 터미널 게이트웨이로 구성됩니다.

`opencode`가 기본 MVP Agent 도구입니다. `caskctl session create`는 기본적으로 `--tool opencode`를 사용하며, Agent 런타임 이미지는 고정 버전의 `opencode-ai` CLI를 포함합니다. 터미널 경로를 결정적으로 테스트할 때는 `stub` 도구를 사용할 수 있습니다.

## 빠른 검증

```bash
make test
make kind-test
```

`make kind-test`는 `agentcask-mvp` kind 클러스터를 생성/사용하고, `cask-api`, `cask-model-proxy`, `cask-controller`, Agent 런타임 로컬 이미지를 빌드 및 로드한 뒤 CRD/RBAC/Deployment를 설치합니다. 이후 `caskctl`로 세션 생성, 터미널 연결, 삭제 흐름을 실행하고, `REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK` 센티널 키가 AgentSession YAML, Agent Pod env, API/CLI 출력, 터미널 출력, 컴포넌트 로그에 노출되지 않는지 확인합니다.

## 사용자가 직접 테스트하는 방법

### 1. 준비물

- Go 1.25+
- Docker
- kind
- kubectl
- 선택: Helm, Helm 차트 설치 경로를 테스트할 때만 필요

현재 MVP는 Web UI가 없습니다. 사용자는 `caskctl`만 사용하며, `caskctl`은 Kubernetes API가 아니라 `cask-api`에만 접속합니다.

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
  --create-namespace
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
export CASK_TOKEN=dev-token
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

## MVP 제약

- Web UI는 구현되어 있지 않습니다.
- 외부로 노출되는 런타임 컴포넌트는 `cask-api`뿐입니다.
- `cask-model-proxy`는 내부 전용이며 upstream 모델/API 키를 보관할 수 있는 유일한 컴포넌트입니다.
- Agent Pod에는 내부 `cask-model-proxy` URL, 짧은 수명의 세션 proxy token, projected service account token만 전달됩니다.
- 세션별 Ingress 또는 public Service는 기본 생성하지 않습니다.
- kind의 Kata isolation 테스트는 plumbing 검증용입니다. `isolation.profile=kata -> pod.spec.runtimeClassName=kata` 매핑만 확인하며 실제 Kata VM 격리를 검증하지 않습니다.

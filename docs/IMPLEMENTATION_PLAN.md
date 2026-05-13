# Implementation Plan: agentcask MVP

## Phase 0. Repository skeleton

Create:

```text
cmd/cask-api/
cmd/cask-model-proxy/
cmd/cask-controller/
cmd/caskctl/
api/v1alpha1/
internal/api/
internal/controller/
internal/terminal/
internal/modelproxy/
internal/isolation/
internal/cli/
config/crd/
config/rbac/
config/samples/
deploy/kind/
charts/agentcask/
examples/
test/e2e/
```

Add:

```text
go.mod
Makefile
README.md
```

Acceptance criteria:

- `go test ./...` runs.
- empty binaries build.

## Phase 1. AgentSession API type and CRD

Implement:

- `AgentSession` type.
- spec/status fields.
- CRD generation.
- sample CRs.

Acceptance criteria:

- CRD YAML generated.
- `kubectl apply -f config/crd` works.
- no secret fields exist in CRD.

## Phase 2. isolationProfiles

Implement:

- isolation profile config type.
- profile validation.
- profile -> PodSpec mapping.
- RuntimeClass existence check.

Acceptance criteria:

- default omits runtimeClassName.
- kata sets runtimeClassName from config.
- unsupported profile fails cleanly.
- tests cover mapping and failure cases.

## Phase 3. cask-controller reconcile

Implement:

- watch AgentSession.
- add finalizer.
- create Agent Pod.
- inject only model proxy URL and proxy token.
- update status.
- cleanup on delete.

Acceptance criteria:

- creating CR creates Pod.
- deleting CR deletes Pod.
- status.phase transitions correctly.
- Pod does not contain real model/API keys.

## Phase 4. cask-api REST API

Implement:

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{id}`
- `DELETE /api/v1/sessions/{id}`
- `/healthz`
- `/readyz`

Acceptance criteria:

- API creates AgentSession.
- API rejects raw `runtimeClassName`.
- API rejects secret-looking request fields.
- API responses do not expose Pod internals by default.

## Phase 5. cask-api terminal gateway

Implement:

- `WSS /api/v1/sessions/{id}/terminal`
- session ownership check.
- session -> pod resolution.
- Kubernetes `pods/exec`.
- binary terminal frames.
- resize control frames.
- timeout handling.

Acceptance criteria:

- fake WebSocket terminal test passes.
- kind E2E can connect to the deterministic stub TUI and the runtime image contains `opencode` for user sessions.

## Phase 6. cask-model-proxy minimal model proxy

Implement:

- internal model proxy route.
- upstream credentials loaded only by `cask-model-proxy`.
- session proxy token validation.
- redaction middleware.

Acceptance criteria:

- Agent Pod uses proxy URL/token.
- upstream key remains only in cask-model-proxy Secret/env.
- negative tests prove no key leak into Pod/CR/API response/logs.

## Phase 7. caskctl

Implement:

- config loading.
- REST client.
- `session create`
- `session list`
- `session get`
- `session connect`
- `session delete`
- WebSocket terminal client.

Acceptance criteria:

- CLI tests pass.
- `caskctl session connect` works against kind deployment.

## Phase 8. kind E2E

Implement:

- kind cluster setup.
- image build/load.
- CRD install.
- deploy cask-api/controller.
- run create/list/connect/delete flow.
- optional kata plumbing RuntimeClass.

Acceptance criteria:

- `make kind-test` passes on developer machine.
- Agent runtime image includes `opencode` while E2E keeps deterministic terminal assertions on the stub adapter.
- docs clearly state real Kata is not validated by kind unless runtime is installed.

## Phase 9. Helm chart packaging

Implement:

- `charts/agentcask` chart metadata, values, and schema.
- CRD install through `crds/`.
- templates for namespaces, ServiceAccounts/RBAC, `cask-api`, `cask-model-proxy`, `cask-controller`, NetworkPolicy, and optional RuntimeClass.
- safe examples for kind values and `AgentSession`.

Acceptance criteria:

- `make helm-lint` passes.
- `make helm-template` renders the chart with CRDs.
- chart install in kind rolls out all three control-plane Deployments.
- `make kind-helm-test` passes.
- `caskctl` can create/connect/delete a session through the Helm-installed `cask-api`.
- no chart values or examples contain real upstream credentials.

## Phase 10. Documentation and prompts

Update:

- README
- runbook
- opencode prompt
- Codex Cloud prompt if needed

Acceptance criteria:

- implementation agents can start from docs without asking for architectural clarification.

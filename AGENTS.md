# AGENTS.md

## Project

This repository implements the **agentcask MVP**.

Product/component naming:

- Project: `agentcask`
- API server: `cask-api`
- Internal model proxy: `cask-model-proxy`
- Controller: `cask-controller`
- CLI: `caskctl`
- CRD Kind: `AgentSession`
- API group: `agentcask.aidev.samsungds.net`

Avoid introducing product names centered on `agent-*` unless referring to the generic concept of AI agents.

## Architecture rules

- `cask-api` is the only externally exposed runtime component.
- `cask-api` includes REST API and WebSocket terminal gateway for MVP.
- `cask-model-proxy` is internal-only and handles minimal model proxy traffic.
- There is no Web UI in the MVP.
- End users must not access Kubernetes API directly.
- End users must not access Agent Pods directly.
- Do not create per-session Ingress by default.
- Do not create per-session public Service by default.
- The Helm chart must not expose `cask-model-proxy` or Agent Pods publicly.
- The Helm chart should install runtime components into the Helm release namespace and keep the session namespace configurable.
- Agent Pods are created by `cask-controller`, not by `cask-api`.
- `AgentSession` is the internal orchestration API.
- `caskctl` talks to `cask-api`, not to the Kubernetes API.

## Security rules

Real model/API keys must never be placed in:

- AgentSession spec/status
- caskctl output
- API responses
- Agent Pod env vars
- Agent Pod mounted files
- terminal streams
- logs

Only `cask-model-proxy` may hold upstream model credentials.

Agent Pods may receive only:

- internal `cask-model-proxy` URL
- short-lived session proxy token
- projected service account token

If a tool requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, use a short-lived proxy token in that env var. Never use a real upstream key.

## Isolation rules

- Use `spec.isolation.profile`.
- Do not expose arbitrary `runtimeClassName` to users.
- Map isolation profiles to RuntimeClass/nodeSelector/tolerations through `isolationProfiles`.
- `default` means omit `Pod.spec.runtimeClassName`.
- `kata` means set `Pod.spec.runtimeClassName` based on controller config.

## Testing rules

Every implementation phase must include tests.

Required test categories:

- unit tests
- API handler tests
- controller reconcile tests
- terminal gateway tests with mocks
- caskctl command tests
- kind-based integration/E2E tests
- negative tests for secret leakage
- Helm chart lint/template checks when chart files change

Do not mark the MVP complete until `make test`, `make helm-lint`, `make helm-template`, `make kind-test`, and `make kind-helm-test` pass.

## Required reading order

1. `PRD.md`
2. `docs/ARCHITECTURE.md`
3. `docs/API_SPEC.md`
4. `docs/CRD_SPEC.md`
5. `docs/SECURITY_MODEL.md`
6. `docs/CLI_SPEC.md`
7. `docs/IMPLEMENTATION_PLAN.md`
8. `docs/TEST_PLAN.md`
9. `docs/HELM.md`

## Implementation preference

Use Go for MVP components unless the repository already mandates otherwise.

Recommended layout:

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

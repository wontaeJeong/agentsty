# AGENTS.md

## Project

This repository develops **agentcask** as a production service. Existing implementation and local tests are a development baseline, not evidence of production readiness.

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

- Currently, `cask-api` is the externally exposed runtime component and includes REST API and the WebSocket terminal gateway. This topology is not permanent.
- Web UI/admin portals, a separate terminal gateway, provider-specific gateways, persistence, OIDC, event-driven reconciliation, dynamic resource/isolation policies, session recovery, multiple agent runtimes, organizations, quota and billing are permitted when justified by product requirements.
- Keep `cask-model-proxy` internal-only. Its capabilities may expand; do not impose a minimum-proxy feature ceiling.
- Use `docs/DESIGN_DECISIONS.md` for justified architecture changes, including threat model, operational tradeoffs and API/CRD compatibility/migration. Do not sacrifice reliability or scalability merely for implementation speed, or add abstraction without a concrete requirement.
- End users must not access Kubernetes API directly.
- End users must not access Agent Pods directly.
- Do not create per-session Ingress by default.
- Do not create per-session public Service by default.
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

Security boundaries remain mandatory regardless of topology: authenticate and authorize every user/session operation, apply least-privilege RBAC, isolate users' and sessions' resources/data, and keep networks private by default. Treat agent code as untrusted; do not run it without isolation appropriate to the threat model. Production security guarantees require deployment-specific evidence, not merely a documented target. Vault, SPIFFE and External Secrets are allowed security integration choices, not mandatory products.

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

`make test` and `make kind-test` are regression baselines, not sufficient production acceptance. Stub/Mock/Fake are for testing and do not prove a real service integration is complete. Every new feature must satisfy `docs/RELEASE_CRITERIA.md`, including real user scenarios, security, failure/recovery, multi-user/session behavior, stable contracts, observability, scalability/maintainability, reproducible configuration/deployment, documentation/runbooks and measurable performance/resource criteria. Record unexecuted checks honestly; never claim production readiness from local kind plumbing alone.

## Required reading order

1. `PRD.md`
2. `docs/ARCHITECTURE.md`
3. `docs/API_SPEC.md`
4. `docs/CRD_SPEC.md`
5. `docs/SECURITY_MODEL.md`
6. `docs/CLI_SPEC.md`
7. `docs/IMPLEMENTATION_PLAN.md`
8. `docs/TEST_PLAN.md`
9. `docs/PRODUCTION_REQUIREMENTS.md`
10. `docs/PRODUCTION_ROADMAP.md`
11. `docs/RELEASE_CRITERIA.md`
12. `docs/DESIGN_DECISIONS.md`

## Implementation preference

Retain Go for core services and Kubernetes CRDs as existing assets. Other components may use appropriate technologies with a documented rationale. Current CLI/OpenCode defaults do not impose permanent client or runtime priorities.

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
test/e2e/
```

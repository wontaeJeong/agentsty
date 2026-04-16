# Architecture

## System shape

`agentsty` is split into clear boundaries:

- `agentsty_api` handles HTTP parsing, response shaping, and FastAPI wiring.
- `agentsty_platform` owns the shared contracts for config, domain, persistence, observability, gateway access, runtimes, executors, and orchestration.
- `agentsty_runtime_opencode` adapts the runtime side to the shared gateway contract and shells out to the real OpenCode CLI.
- `agentsty_executor_kubernetes` adapts sandbox execution to the shared executor contract.

Transport concerns stay out of the platform layer. That keeps the API thin and leaves the orchestration path reusable from other entry points later.

## Request flow

1. `POST /v1/chat/completions` lands in `agentsty_api`.
2. API auth resolves the effective tenant from either anonymous local access or a verified principal.
3. The API builds tenant scoped domain identifiers and trace context.
4. `agentsty_platform.services.ExecutionOrchestrator` applies intake, policy, persistence, runtime, and executor steps.
5. The runtime adapter launches headless OpenCode, which reaches the internal gateway through the shared gateway client.
6. The executor boundary creates or launches isolated sandbox work.
7. Repository and artifact stores record job state, audit events, and results.

## Trust boundaries

- API to platform, HTTP input is treated as untrusted until it is turned into typed shared contracts.
- API to identity, non-local requests need bearer auth or an already verified principal on the request state.
- Platform to gateway, model access stays behind the internal gateway client and allowlist checks.
- Platform to executor, sandbox creation is controlled by the executor boundary, not by the HTTP layer.
- Tenant boundaries, every request, job, and identifier carries tenant scope in the domain layer.

## Local versus production

Local development uses process isolation and local doubles where needed so the repo stays easy to run and test.

Dev, staging, and production use the non-local Kubernetes and Kata shaped path in this repo. The manifests and adapter cover network policy, namespace separation, quotas, limit ranges, tenant RBAC, default-deny sandbox policies, runtimeClass settings, and the configured Kubernetes API client seam that drives sandbox lifecycle operations.

The current built-in non-local persistence backend is SQLite-backed, with package-local migrations under `agentsty_platform.persistence.migrations` and lazy initialization on first write. Unsupported PostgreSQL URLs are rejected explicitly instead of being rewritten to SQLite, which keeps the persistence contract production-honest. Because that backend is single-writer, the shipped non-local API Deployment posture is intentionally single-replica until a stronger persistence backend is added.

The OpenCode runtime path is also real now. The adapter prepares a headless session, runs `opencode serve`, attaches with `opencode run`, and exports the session afterward. A compatibility proxy can sit in front of the internal gateway when the subprocess path needs SSE normalization.

## Data and state

- Job state lives behind repository contracts.
- Artifact metadata is separate from artifact bytes, and non-local execution now persists both through the durable repository plus artifact-content-store path.
- Audit metadata is appended as immutable events.
- Observability data uses structured payloads with redaction rules for obvious secrets.
- Non-local job, idempotency, audit, and artifact metadata persist in SQLite tables, while artifact bytes are stored under the configured artifact root and returned to callers as artifact references in the public API.

## Design goals

- Keep the north-south API small.
- Keep runtime and executor adapters replaceable.
- Keep tenant scope visible in every core identifier.
- Keep local development fast without pretending it is production isolation.
- Keep the production path honest about supported backends and operator-owned environment concerns.

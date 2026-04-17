# Architecture

## Overview

`agentsty` is a Phase 1 MVP for a runtime-agnostic agent execution service.

The current implementation intentionally focuses on one small vertical slice:

1. FastAPI receives an HTTP request.
2. The HTTP layer validates and translates the payload into an internal `ExecutionRequest`.
3. The application layer orchestrates runtime preparation and sandbox execution.
4. A stub runtime and a stub sandbox executor produce a deterministic result.
5. The HTTP layer maps the internal `ExecutionResult` back to an API response.

This is not a production system yet. It is a minimal foundation that makes future runtime and sandbox replacements explicit.

## Architectural Goals

- keep the Phase 1 slice small and testable
- separate HTTP, orchestration, domain contracts, and infrastructure adapters
- allow future runtime adapters without changing the public HTTP contract
- allow future sandbox executors without rewriting application orchestration
- validate configuration early enough to fail startup on unsupported runtime or sandbox settings

## Repository Structure

```text
apps/
  api/
    main.py
src/
  agentsty/
    application/
      errors.py
      services/execution_service.py
    domain/
      execution.py
      ports.py
    infrastructure/
      config/settings.py
      executors/stub.py
      runtimes/opencode.py
    interfaces/http/
      dependencies.py
      schemas.py
      routes/
        health.py
        chat_completions.py
    bootstrap.py
tests/
  unit/
  integration/
  e2e/
docs/
ops/
```

## Layer Responsibilities

### 1. HTTP Layer

Files:

- `apps/api/main.py`
- `src/agentsty/interfaces/http/schemas.py`
- `src/agentsty/interfaces/http/routes/health.py`
- `src/agentsty/interfaces/http/routes/chat_completions.py`
- `src/agentsty/interfaces/http/dependencies.py`

Responsibilities:

- expose FastAPI endpoints
- validate request/response payloads
- convert HTTP input into internal request objects
- convert application errors into HTTP errors
- read the already-validated `ExecutionService` from app state

### 2. Application Layer

Files:

- `src/agentsty/application/services/execution_service.py`
- `src/agentsty/application/errors.py`

Responsibilities:

- orchestrate the runtime and sandbox collaboration
- keep orchestration independent from FastAPI details
- normalize runtime/sandbox failures into application-level execution errors

This is the central use-case layer for Phase 1.

### 3. Domain Layer

Files:

- `src/agentsty/domain/execution.py`
- `src/agentsty/domain/ports.py`

Responsibilities:

- define the internal execution contract
- define the execution result contract
- define the runtime and sandbox interfaces

Key domain types:

- `TenantId`
- `ExecutionRequest`
- `PreparedExecution`
- `SandboxExecutionRecord`
- `ExecutionResult`
- `Artifact`
- `SandboxExecutor`
- `AgentRuntime`

The domain layer does not depend on FastAPI or infrastructure implementation details.

### 4. Infrastructure Layer

Files:

- `src/agentsty/infrastructure/config/settings.py`
- `src/agentsty/infrastructure/executors/stub.py`
- `src/agentsty/infrastructure/runtimes/opencode.py`
- `src/agentsty/bootstrap.py`

Responsibilities:

- load settings from environment variables
- instantiate supported runtime and sandbox implementations
- provide the current stub executor/runtime adapters
- fail fast on invalid runtime or sandbox configuration

Phase 1 implementations:

- `OpenCodeRuntime`
- `StubSandboxExecutor`

These are intentionally stubbed. They exist to prove the seams, not to provide real sandboxing or real agent-runtime integration.

## Request Flow

### `GET /health`

1. FastAPI app is already created.
2. `build_execution_service()` has already run during app startup.
3. The route returns `{"status": "ok"}`.

Because startup constructs the execution service eagerly, invalid runtime or sandbox configuration fails application startup before the health route can falsely report readiness.

### `POST /v1/chat/completions`

1. FastAPI validates `tenant_id`, `message`, and optional `metadata`.
2. The route creates an `ExecutionRequest` with a generated `request_id`.
3. The route resolves the shared `ExecutionService` from `app.state`.
4. `ExecutionService.execute()` calls:
   - `AgentRuntime.prepare(request)`
   - `SandboxExecutor.execute(prepared_execution)`
   - `AgentRuntime.build_result(request, sandbox_record)`
5. The route maps `ExecutionResult` into `ChatCompletionResponse`.
6. If runtime or sandbox execution fails, the route returns an HTTP `502`.

## Configuration Model

The environment-backed settings live in `src/agentsty/infrastructure/config/settings.py`.

Supported settings:

- `AGENTSTY_APP_ENV`
- `AGENTSTY_LOG_LEVEL`
- `AGENTSTY_DEFAULT_TIMEOUT_SECONDS`
- `AGENTSTY_DEFAULT_RUNTIME`
- `AGENTSTY_SANDBOX_MODE`
- `AGENTSTY_INTERNAL_LLM_PROXY_BASE_URL`

In Phase 1, only these runtime/sandbox values are supported:

- runtime: `opencode`
- sandbox: `stub`

Unsupported values cause startup failure.

## Testing Strategy

### Unit Tests

`tests/unit/` covers:

- domain models
- HTTP schemas
- stub sandbox executor
- stub runtime
- execution service

### Integration Tests

`tests/integration/` covers:

- `GET /health`
- `POST /v1/chat/completions`
- failure translation and invalid configuration regression checks

### E2E Tests

`tests/e2e/test_live_api.py` boots a live Uvicorn server and exercises the HTTP API over a real socket.

This gives the MVP three levels of verification:

- unit
- integration
- live-server E2E

## Current Extension Points

### Future Runtime Adapters

Future runtimes should implement `AgentRuntime`, for example:

- `ClaudeCodeRuntime`
- `CodexRuntime`
- a real external `OpenCodeRuntime` adapter

### Future Sandbox Executors

Future executors should implement `SandboxExecutor`, for example:

- `LocalProcessSandboxExecutor`
- `KubernetesJobSandboxExecutor`
- `KataSandboxExecutor`
- `OpenShellSandboxExecutor`

## Phase 1 Constraints

This architecture intentionally does **not** include:

- persistent job storage
- async job queues
- authentication or authorization
- database dependencies
- real sandbox isolation
- real external runtime integration
- production deployment concerns

Those belong to later phases after the current MVP contract has been validated.

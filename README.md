# agentsty

`agentsty` is a Phase 1 MVP foundation for a runtime-agnostic agent execution service.

## Phase 1 Scope

This repository intentionally implements the smallest vertical slice that proves the architecture:

- FastAPI receives a request
- HTTP input is mapped to an internal execution request
- a pluggable `AgentRuntime` prepares work for a pluggable `SandboxExecutor`
- a stub `OpenCodeRuntime` and a stub sandbox executor produce a deterministic response
- the result is returned through `POST /v1/chat/completions`

This is a first-commit MVP, not a production-ready platform.

## Current Stub Implementations

- `OpenCodeRuntime` is a stub adapter that prepares and materializes a deterministic response.
- `StubSandboxExecutor` is a local in-process executor stub, not a real security boundary.

## Project Structure

```text
apps/
  api/
src/
  agentsty/
    application/
    domain/
    infrastructure/
    interfaces/http/
tests/
  integration/
  unit/
docs/
ops/
```

## Run

```bash
uv sync --dev
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

### Health Check

```bash
curl -s http://127.0.0.1:8000/health
```

### Chat Completions

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"tenant-demo","message":"hello phase1","metadata":{"trace_id":"demo-1"}}'
```

## Test and Quality Checks

```bash
uv run ruff check .
uv run mypy src apps tests
uv run pytest -q
```

## Phase 2 Direction

- add real sandbox executors such as Kubernetes job, Kata, or OpenShell backed implementations
- add additional runtimes such as Claude Code and Codex adapters
- add asynchronous job orchestration only when operationally necessary
- harden tenancy, auth, persistence, and deployment workflows after MVP validation

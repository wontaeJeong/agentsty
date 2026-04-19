# AGENTS.md

This repository is designed for AI coding agents and human engineers working together on a production-oriented internal sandbox platform.

## Core implementation rules

- Use `uv` for dependency and workspace management.
- Keep Python at 3.12+.
- Maintain strong typing. Prefer typed models, `Protocol`s, enums, and explicit service contracts.
- Prefer Pydantic models, dataclasses, or typed aliases over raw `dict[str, Any]` payloads.
- Keep orchestration, proxy, sandbox, storage, and provider concerns separate.
- Do not bypass security assumptions for convenience.
- Do not introduce hidden coupling across packages or cross-layer imports that violate the architecture.
- Do not put raw secret values in sandbox-facing or agent-facing models.
- Treat the sandbox runtime as untrusted.

## Change management rules

- Favor incremental changes over destructive rewrites.
- Avoid giant files and avoid collapsing package boundaries.
- When architecture changes, update `README.md`, `PRD.md`, and the relevant `docs/*.md` files in the same change.
- Stub implementations must remain removable and replaceable.
- Keep TODO markers explicit where real policy, persistence, or runtime integrations will later be added.

## Quality gates

Before finalizing changes, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

## Architecture expectations

- Control plane owns identity, policy, metadata, and lifecycle orchestration.
- Proxy plane owns secret mediation and controlled outbound access.
- Execution plane owns isolated runtime execution only.
- Shared packages define contracts and models; apps compose implementations.
- All run/session/job/artifact state must remain tenant-aware.

## What to avoid

- Hidden global state for tenant or request ownership.
- Provider-specific logic embedded directly into sandbox code.
- Stringly typed lifecycle state machines when enums or literals are appropriate.
- Over-implementation of fake business logic in bootstrap code.
- Destructive architecture rewrites without written justification.

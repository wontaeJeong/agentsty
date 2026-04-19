# AGENTS.md

This file defines repository rules for AI coding agents and human contributors working in `agentsty`.

## Mission

Build a maintainable, strongly typed, security-conscious foundation for a multi-tenant AI agent sandbox platform.
Optimize for long-term architecture quality, trust-boundary preservation, and future extensibility rather than short-term demo speed.

## Workflow rules

1. Use `uv` for Python dependency and workspace management.
2. Keep changes incremental and legible.
3. Update docs when architecture or boundary assumptions change.
4. Prefer repository-wide consistency over isolated local cleverness.
5. Before finalizing implementation work, run Ruff, mypy, and pytest.

## Architecture rules

Keep these concerns separate:

- API / control plane
- proxy / secret mediation
- sandbox execution
- storage
- agent abstraction and orchestration
- shared domain models and focused common primitives

Do not collapse these boundaries for convenience.

## Typing rules

- Prefer Pydantic models, dataclasses, enums, TypedDict, Protocol, and ABCs where appropriate.
- Prefer explicit domain models over loose dictionaries.
- Prefer enums, constants, and literals over repeated ad hoc strings.
- Prefer constructor injection or explicit dependency wiring over hidden global coupling.
- Treat raw `dict` use for core domain entities as a design bug unless clearly justified.

## Security rules

- Treat sandbox runtimes as untrusted by default.
- Never put provider API keys or privileged internal service credentials inside sandbox runtime configuration.
- Never assume unrestricted outbound network access from the sandbox.
- Never silently weaken tenant isolation or trust boundaries for convenience.
- Do not blur proxy and sandbox responsibilities.

## Repository hygiene rules

- Keep modules focused and small.
- Avoid vague names like `misc`, `helper`, or `utils` unless the scope is genuinely narrow and obvious.
- Do not create a dumping-ground `common` package.
- Avoid destructive rewrites without strong reason.
- Document deferred work explicitly with scoped TODOs only when the boundary is already correct.

## Documentation rules

- README should remain concise and useful.
- `PRD.md` is a working engineering/product document, not a business-only artifact.
- `docs/architecture.md` and `docs/security.md` are canonical for trust boundaries.
- `docs/testing.md` should define validation strategy before broad implementation grows.

## Review checklist before finalizing changes

Confirm that:

1. Security assumptions are still intact.
2. Tenant isolation was not weakened.
3. Concrete implementations do not leak through abstraction boundaries.
4. New code remains strongly typed.
5. Docs were updated if architecture changed.
6. Ruff, mypy, and pytest have been run where code exists.

## Forbidden shortcuts

- Do not hardcode one agent backend into orchestration interfaces.
- Do not pass important state around as undocumented strings.
- Do not use untyped `Any`-heavy structures when a clear model should exist.
- Do not claim security guarantees not actually implemented.
- Do not introduce convenience paths that bypass secret mediation.

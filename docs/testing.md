# Testing Strategy

## 1. Testing goals

Testing in this repository exists to prove that architectural boundaries, typing discipline, and security-sensitive behavior hold as the system evolves.
The repository should favor tests that validate contracts and isolation assumptions over shallow coverage metrics.

## 2. Unit test strategy

Unit tests should cover:

- domain models and validation rules,
- lifecycle state transitions,
- configuration parsing and error handling,
- small boundary-focused implementations,
- policy decisions that do not require external systems.

Unit tests should remain fast, deterministic, and strongly typed.

## 3. Integration test strategy

Integration tests should validate:

- API wiring to application services,
- proxy request mediation behavior,
- sandbox lifecycle coordination through interfaces,
- storage implementations against shared contracts,
- cross-package behavior where multiple boundaries interact.

Integration tests must avoid pretending that a local stub proves production isolation.

## 4. End-to-end direction

E2E testing is a later phase, but the direction is clear:

- create a tenant-scoped request,
- launch a job,
- exercise sandbox lifecycle,
- route privileged access through the proxy,
- validate resulting metadata, artifacts, and audit traces.

E2E tests should focus on realistic boundary behavior rather than frontend polish.

## 5. Contract tests for abstractions

Contract tests are first-class in this repository.
They should verify that swappable implementations satisfy shared behavior for:

- agent runtime interfaces,
- sandbox management interfaces,
- storage interfaces,
- configuration and lifecycle contracts.

This matters because extensibility is a design goal, not a future aspiration.

## 6. Security-oriented testing

The repository should include targeted tests for:

- tenant isolation enforcement,
- secret non-exposure to sandbox-facing configuration,
- denial-by-default network policy assumptions,
- redaction and logging safety,
- sandbox and proxy boundary behavior.

Security tests should be treated as product requirements, not optional hardening work.

## 7. Sandbox lifecycle tests

Sandbox-related tests should validate:

- lifecycle transitions,
- ownership and tenant scoping,
- cleanup behavior,
- failure handling,
- artifact collection boundaries,
- stub behavior that clearly signals where real isolation remains deferred.

## 8. Mock and stub rules

- Stubs are acceptable when the boundary is modeled correctly.
- Mocks should not hide architectural problems.
- Development implementations must be explicit about what they do **not** guarantee.
- Tests should avoid overfitting to local filesystem behavior if storage is intended to be abstract.

## 9. CI quality gates

The default CI quality gates for code-bearing passes should include:

- Ruff linting,
- mypy with strict settings,
- pytest,
- targeted contract and integration tests as the scaffold grows.

Failing type checks or security-relevant tests should block merges.

## 10. Testing progression by phase

### Foundation phase

- validate docs completeness and repository conventions informally,
- define quality gates and testing strategy.

### Scaffold phase

- add unit tests for typed domain models,
- add contract tests for abstractions,
- add smoke tests for FastAPI health endpoints.

### Hardening phase

- add integration and security regression tests,
- add sandbox lifecycle and tenant-isolation test suites.

## 11. Definition of done for implementation passes

For code-bearing changes, work is not complete until:

1. relevant tests are added or updated,
2. Ruff passes,
3. mypy passes,
4. pytest passes,
5. any deferred security limitations are documented honestly.

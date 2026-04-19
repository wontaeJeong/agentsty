# Testing strategy

## Goals

The testing strategy should validate both software correctness and architecture invariants. For this platform, interface boundaries and security defaults matter as much as endpoint behavior.

## Test layers

### Unit tests

Unit tests cover:

- shared ownership and identifier models
- enum and settings behavior
- agent registry behavior
- sandbox policy defaults
- storage and artifact model validation

### Integration tests

Integration tests cover:

- API app startup and health endpoints
- proxy app startup and health endpoints
- placeholder lifecycle routes returning stable typed responses

### End-to-end tests

Later end-to-end tests should exercise:

- run submission through the API
- policy evaluation
- sandbox lifecycle transitions
- proxy-mediated provider access
- artifact persistence and retrieval

The bootstrap does not implement full e2e behavior yet, but the architecture should remain ready for it.

## Contract tests for abstraction layers

Contract tests are required for:

- agent protocol implementations
- sandbox backend implementations
- storage implementations
- proxy mediation behavior

The point is to ensure swappable implementations can be introduced without changing the consuming application logic.

## Security-oriented tests

Important early tests include:

- network policy defaults to deny
- sandbox request models only accept secret references, not raw secret values
- all execution and persistence models carry tenant ownership metadata
- proxy and API health routes do not leak sensitive configuration

## Sandbox lifecycle tests

As real implementations arrive, add tests for:

- sandbox provisioning and teardown
- timeout handling
- cleanup after failed execution
- capability application and policy enforcement

## Mock and stub strategy

- Keep stubs intentionally small and obvious.
- Stubs should model interfaces and defaults, not emulate production behavior.
- Do not let tests depend on undocumented stub behavior.
- Concrete adapters should be testable against shared contract suites.

## CI expectations

CI should run:

- Ruff linting
- Ruff format check
- mypy strict checks
- pytest

Over time CI should expand to include contract suites for concrete adapters and any containerized sandbox tests needed for hardened runtimes.

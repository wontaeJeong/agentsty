# Roadmap

## Phase 1: Foundation

Goal: establish the repository as a secure, extensible, documentation-led foundation.

Deliverables:

- top-level product and engineering docs,
- architecture and security boundaries,
- testing strategy,
- phased roadmap,
- proposed repository structure.

Exit criteria:

- foundational docs are present and aligned,
- the separation between control plane, proxy, sandbox, storage, agent abstractions, and shared models is explicit,
- major open questions are documented rather than hidden.

## Phase 2: MVP skeleton

Goal: scaffold a strongly typed codebase that matches the documented architecture.

Deliverables:

- uv-managed multi-package workspace,
- FastAPI app skeletons for API and proxy,
- shared domain models,
- agent, sandbox, and storage interfaces,
- safe stub implementations,
- CI and local quality tooling.

Exit criteria:

- repository structure exists on disk,
- code boundaries match the architecture docs,
- strict linting, typing, and basic tests are running.

## Phase 3: Hardening and security

Goal: turn the safe skeleton into a more trustworthy execution foundation.

Deliverables:

- stronger sandbox lifecycle enforcement,
- policy-aware proxy mediation,
- tenant-isolation validation,
- security-oriented tests and audit improvements,
- clearer operational constraints.

Exit criteria:

- key security assumptions are backed by implementation and tests,
- tenant scoping is explicit across core flows,
- deferred high-risk areas have concrete plans or implementations.

## Phase 4: Extensibility

Goal: make replacement and expansion of major subsystems straightforward.

Deliverables:

- multiple agent backend implementations,
- more than one storage and/or sandbox implementation path,
- richer contract tests,
- clearer capability modeling for runtimes.

Exit criteria:

- orchestration remains independent from concrete backends,
- new implementations can be added without architectural rewrites.

## Phase 5: Operational maturity

Goal: prepare the platform for sustained internal use.

Deliverables:

- stronger observability and auditability,
- clearer deployment and runtime policies,
- runbooks and operational docs,
- quota, policy, and lifecycle controls as needed.

Exit criteria:

- the platform has a clear path to routine internal operation,
- operational expectations are documented and testable where possible.

## Cross-phase risks

- unclear tenant identity model,
- insufficiently scoped proxy responsibilities,
- local development assumptions hardening into architecture,
- `packages/common` growing into a dumping ground,
- deferring authn/authz decisions for too long.

## Near-term next steps

1. Scaffold the proposed repository layout.
2. Add typed domain and abstraction skeletons.
3. Add tooling configuration and CI.
4. Start contract and smoke tests early.

## Decision log reminders

Before deeper implementation, resolve or narrow:

- canonical tenant identity,
- initial sandbox technology choice,
- first storage backend target,
- first provider/proxy policy shape,
- authn/authz approach for internal users and services.

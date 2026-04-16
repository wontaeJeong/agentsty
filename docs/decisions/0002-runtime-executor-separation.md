# ADR 0002, keep runtime and executor concerns separate

Status: accepted

## Context

Agent runtime work and sandbox execution are related, but they are not the same responsibility. Mixing them would make it harder to swap adapters, test one side in isolation, and reason about trust boundaries.

## Decision

Keep runtime adapters under `agentsty_runtime_opencode` and executor adapters under `agentsty_executor_kubernetes`, with shared contracts in `agentsty_platform`.

## Consequences

- The runtime talks to the internal gateway without knowing executor details.
- The executor manages sandbox lifecycle without knowing FastAPI details.
- Shared orchestration can compose both sides cleanly.
- Local doubles stay easy to test.

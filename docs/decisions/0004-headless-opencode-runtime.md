# ADR 0004, run OpenCode headlessly through the real CLI path

Status: accepted

## Context

The runtime adapter needed to be real enough for production-shaped behavior while still fitting the internal gateway boundary and the repo's local verification model.

## Decision

Use the installed `opencode` CLI in headless mode. The adapter starts `opencode serve`, attaches with `opencode run`, exports the session, and keeps gateway access behind the shared internal client. When needed, a compatibility proxy can normalize the gateway stream without changing the adapter contract.

## Consequences

- The runtime path now exercises the actual CLI process instead of a local stub.
- Gateway access still stays inside the platform client boundary.
- Session export and cleanup are part of the real runtime flow.
- Repo tests can keep using bounded command runners without weakening the production adapter contract.

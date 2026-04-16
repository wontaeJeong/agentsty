# ADR 0003, back non-local persistence with SQLite and tracked migrations

Status: accepted

## Context

Non-local profiles needed durable storage that behaved like production state without pretending the repo already had a live external database service wired end to end.

## Decision

Use a SQLite-backed persistence store for non-local jobs, idempotency, audit events, and artifact metadata. Keep package-local SQL migrations under `agentsty_platform.persistence.migrations`, initialize the database lazily on first write, and preserve the exported `Persistent*` repository names for compatibility.

## Consequences

- Non-local runs now have durable repository state instead of snapshot wrappers.
- Schema changes stay explicit and testable in SQL.
- Startup stays light because migrations run only when the store is first used.
- The manifest database URL remains a deployment contract, but the current repo implementation still resolves non-local persistence to SQLite.

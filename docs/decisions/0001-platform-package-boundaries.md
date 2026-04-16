# ADR 0001, replace scaffold package boundaries with platform boundaries

Status: accepted

## Context

The repository started as a uv workspace scaffold with shared and worker style template packages. That shape did not match the real platform being built.

## Decision

Move the shared code into `agentsty_platform`, keep `agentsty_api` as the transport layer, and split runtime and executor adapters into their own packages.

## Consequences

- Shared contracts now live in one place.
- The API stays thin.
- Runtime and executor concerns can evolve without leaking into the shared domain.
- The docs and package names now describe the product, not the scaffold.

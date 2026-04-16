# agentsty

`agentsty` is a Python platform for multi-tenant agent runs behind a FastAPI chat-completions style API.

It separates the API, shared platform contracts, OpenCode runtime execution, and Kubernetes sandbox execution so the production path stays clear and testable.

## What lives where

- `packages/platform`, shared domain, config, persistence, observability, gateway, orchestration, runtime, and executor contracts
- `packages/api`, HTTP parsing, auth, dependency wiring, and route handlers
- `packages/runtime-opencode`, the headless OpenCode runtime adapter
- `packages/executor-kubernetes`, the sandbox executor boundary
- `deploy/k8s/`, manifest bundles for local, dev, staging, and prod
- `deploy/images/`, in-repo Docker build definitions for the API and sandbox images
- `tests/`, unit, integration, e2e, and manifest/build-asset checks

## Current production shape

- Local mode uses process isolation, anonymous access when allowed, and local doubles where the developer path needs them.
- Non-local modes require auth, bind tenants to verified principals, use the internal gateway, and run the OpenCode adapter headlessly through the real CLI process path.
- Non-local persistence uses the durable SQL repository path directly, applies package-local migrations lazily, rejects unsupported PostgreSQL URLs instead of rewriting them, and stores artifact bytes under `persistence.artifact_root` with content references persisted alongside artifact metadata.
- The Kubernetes manifests and non-local control-plane adapter are part of the implemented production path in this repo; rolling them onto a live cluster is still an environment-specific operator step rather than a separate code path.
- While non-local persistence remains SQLite-backed, the control-plane Deployment stays single-replica in dev, staging, and production; scaling beyond one API replica requires a multi-writer persistence backend.

## Quick start

```bash
uv sync --all-packages --dev
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run mypy .
uv build --all-packages --out-dir dist --clear --no-create-gitignore
IMAGE_TAG=dev ./deploy/images/build-images.sh
uv run pre-commit run --all-files
uv run pip-audit --progress-spinner off
```

## Runtime modes

- `local`, process isolation, local gateway transport, anonymous local access when enabled
- `dev`, `staging`, and `production`, JWT auth, internal HTTPS gateway access, Kubernetes sandbox execution, durable non-local persistence, and artifact references surfaced in API responses

## Docs

- [Architecture](docs/architecture.md)
- [Security](docs/security.md)
- [Operations](docs/operations.md)
- [Testing](docs/testing.md)
- [Deployment](docs/deployment.md)
- [Container builds](deploy/images/README.md)
- [ADRs](docs/decisions/)

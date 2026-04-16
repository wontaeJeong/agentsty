# Testing

## Test layers

- Unit tests, shared contracts and small rules in `tests/unit/`
- Integration tests, seam crossing checks in `tests/integration/`
- E2E tests, scenario coverage from the public API in `tests/e2e/`
- Deployment asset tests, manifest shape checks in `tests/test_deploy_assets.py`
- Lower-level smoke tests also live at the repo root for the API, runtime adapter, executor adapter, and local development path.

## Main commands

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e
uv run mypy .
uv build --all-packages --out-dir dist --clear --no-create-gitignore
uv run pre-commit run --all-files

## Optional dependency audit

```bash
uv run pip-audit --progress-spinner off
```
```

## What each layer proves

Unit tests cover config defaults, tenant scoped domain rules, gateway policy, SQLite persistence contracts, runtime contracts, and service serialization.

Integration tests cover API to service wiring, orchestration lifecycle behavior, runtime to gateway behavior, and timeout or cancellation handling.

E2E tests cover the public chat completions path for success, rejection, sandbox failure, gateway failure, timeout, cancellation, and tenant isolation.

## Manifest checks

The deployment test suite loads the YAML under `deploy/k8s/` and checks:

- required resource kinds exist in every environment
- config keys line up with the settings contract
- local and non-local security posture differs where it should
- non-local sandboxes declare Kata shaped runtime settings and deny by default network policy
- non-local API Deployments use in-cluster Kubernetes auth consistently and stay single-replica while SQLite backs the control plane
- non-local manifests pin supported `sqlite:///` URLs and mount the service-state root from the same NFS-backed durable volume in both the API pod and sandbox jobs

## Confidence notes

The tests exercise the current code and the manifest contract. Some production behaviors are still covered through control-plane seams, so the suite proves the shape and wiring, not a live cluster rollout.

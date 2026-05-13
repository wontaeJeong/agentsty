# CI/CD

The repository uses GitHub Actions for the MVP delivery checks.

## CI

The `CI` workflow runs on pushes and pull requests. It verifies:

- Go formatting.
- `go mod tidy` cleanliness.
- `make test`.
- `make build`.
- local container image builds for `cask-api`, `cask-model-proxy`, `cask-controller`, and the Agent runtime.
- Helm chart linting and template rendering for `charts/agentcask`.
- kind manifest rendering with `kubectl kustomize`.

## kind E2E

The `kind E2E` workflow runs on demand and for pull requests that touch runtime, manifest, build, or E2E paths. It runs `make kind-test`, which creates or reuses a kind cluster, builds images, loads them into kind, deploys the MVP stack, executes the create/connect/delete flow, validates the separated `cask-model-proxy`, and runs secret-leak assertions.

## CD

The `CD` workflow runs on `v*` tags or manual dispatch. It builds Linux binaries and publishes version-tagged images to GHCR:

- `cask-api`
- `cask-model-proxy`
- `cask-controller`
- `agent-runtime`

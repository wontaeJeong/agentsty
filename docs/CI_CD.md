# CI/CD

The repository uses GitHub Actions for baseline delivery checks. This document describes existing automation, not a claim that [Production Quality Gate](RELEASE_CRITERIA.md) is already automated or satisfied.

## CI

The `CI` workflow runs on pushes and pull requests. It verifies:

- Go formatting.
- `go mod tidy` cleanliness.
- `make test`.
- `make build`.
- local container image builds for `cask-api`, `cask-model-proxy`, `cask-controller`, and the derived Agent runtime.
- `make runtime-test` verifies OpenCode, Git, SSH, and a persistent tmux session as the non-root runtime user.
- Helm chart linting and template rendering for `charts/agentcask`.
- kind manifest rendering with `kubectl kustomize`.

## kind E2E

The `kind E2E` workflow runs on demand and for pull requests that touch runtime, manifest, build, or E2E paths. It runs `make kind-test`, which creates or reuses a kind cluster, builds and loads local control-plane and derived runtime images, deploys the baseline stack, executes the create/connect/delete flow, validates the separated `cask-model-proxy`, and runs secret-leak assertions. Port forwards use automatically allocated local ports.

Stub-based terminal checks and fake RuntimeClass mapping do not validate real providers or Kata isolation. Local kind/CI success does not demonstrate production identity, multitenancy, HA, recovery or performance. `make test` skips opt-in E2E unless explicitly enabled; documentation-only PRs may not trigger kind automatically.

## CD

The `CD` workflow runs on `v*` tags or manual dispatch. It builds Linux binaries and publishes version-tagged images to GHCR:

- `cask-api`
- `cask-model-proxy`
- `cask-controller`
- `agent-runtime`

Publishing binaries/images or creating a version tag is not production release approval. Each production release needs reviewed real-environment evidence, support/compatibility scope and operational guidance under Release Criteria. Follow-up automation is tracked by [Production Roadmap](PRODUCTION_ROADMAP.md).

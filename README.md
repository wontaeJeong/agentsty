# agentcask MVP

`agentcask` is a CLI-first Kubernetes platform for isolated interactive agent sessions. The MVP includes `cask-api`, internal `cask-model-proxy`, `cask-controller`, `caskctl`, an `AgentSession` CRD, and a WebSocket terminal gateway.

Quick local checks:

```bash
make test
make kind-test
```

`make kind-test` creates/uses a kind cluster named `agentcask-mvp`, builds and loads local images for `cask-api`, `cask-model-proxy`, `cask-controller`, and the Agent runtime, installs CRDs/RBAC/deployments, runs a create/connect/delete flow through `caskctl`, validates the separated model proxy, and checks that the sentinel upstream key `REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK` does not appear in AgentSession YAML, Agent Pod env, API/CLI output, terminal output, or component logs.

CI/CD is provided through GitHub Actions: `CI` runs formatting, module tidiness, tests, binary builds, image builds, and manifest rendering; `kind E2E` runs the local kind flow for relevant changes; `CD` publishes version-tagged images to GHCR. See `docs/CI_CD.md`.

Kata isolation in kind is plumbing-only: the test installs a fake `RuntimeClass` named `kata` with handler `runc`. This validates `isolation.profile=kata -> pod.spec.runtimeClassName=kata`; it does not validate real Kata VM isolation.

No Web UI is implemented. End users interact through `caskctl`, which talks only to `cask-api`; `cask-model-proxy` is internal-only, and Agent Pods are not exposed with per-session Ingress or public Services.

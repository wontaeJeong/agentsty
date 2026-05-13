# agentcask MVP

`agentcask` is a CLI-first Kubernetes platform for isolated interactive agent sessions. The MVP includes `cask-api`, internal `cask-model-proxy`, `cask-controller`, `caskctl`, an `AgentSession` CRD, and a WebSocket terminal gateway.

`opencode` is the primary MVP agent tool. `caskctl session create` defaults to `--tool opencode`, and the Agent runtime image installs the pinned `opencode-ai` CLI. The deterministic `stub` tool remains available for E2E terminal testing.

Quick local checks:

```bash
make test
make helm-lint
make helm-template
make kind-test
make kind-helm-test
```

`make kind-test` creates/uses a kind cluster named `agentcask-mvp`, builds and loads local images for `cask-api`, `cask-model-proxy`, `cask-controller`, and the Agent runtime, installs CRDs/RBAC/deployments, runs a create/connect/delete flow through `caskctl`, validates the separated model proxy, and checks that the sentinel upstream key `REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK` does not appear in AgentSession YAML, Agent Pod env, API/CLI output, terminal output, or component logs.

For manual local `caskctl` testing in kind, including `port-forward`, `CASK_API_SERVER`, and `session connect`, see `docs/KIND_TESTING.md`. The MVP Helm chart lives in `charts/agentcask`; see `docs/HELM.md` for install, upgrade, uninstall, values, CRD, and secret guidance.

CI/CD is provided through GitHub Actions: `CI` runs formatting, module tidiness, tests, binary builds, image builds, and manifest rendering; `kind E2E` runs the local kind flow for relevant changes; `CD` publishes version-tagged images to GHCR. See `docs/CI_CD.md`.

Kata isolation in kind is plumbing-only: the test installs a fake `RuntimeClass` named `kata` with handler `runc`. This validates `isolation.profile=kata -> pod.spec.runtimeClassName=kata`; it does not validate real Kata VM isolation.

No Web UI is implemented. End users interact through `caskctl`, which talks only to `cask-api`; `cask-model-proxy` is internal-only, and Agent Pods are not exposed with per-session Ingress or public Services.

# kind Testing Guide

## 1. Purpose

kind tests validate the MVP control plane and terminal path locally.

The E2E flow uses the deterministic `stub` tool for terminal assertions, but it also checks that the Agent runtime image contains the primary MVP CLI, `opencode`.

They do not validate real Kata VM isolation unless the host/kind node is configured with an actual Kata runtime.

## 2. Expected make targets

```bash
make kind-up
make kind-load
make kind-deploy
make kind-test
make kind-down
```

A single command should run everything:

```bash
make kind-test
```

## 3. Test cluster setup

Recommended kind cluster name:

```text
agentcask-mvp
```

Recommended namespace:

```text
agentcask-system
agentcask-sessions
```

## 4. RuntimeClass plumbing test

For kind-only profile plumbing, use:

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata
handler: runc
```

This is not real Kata. It only proves:

```text
isolation.profile=kata -> pod.spec.runtimeClassName=kata
```

Real Kata tests must run in a real RuntimeClass-enabled cluster.

## 5. E2E script outline

```bash
kind create cluster --name agentcask-mvp
docker build -t agentcask/cask-api:dev -f build/cask-api.Dockerfile .
docker build -t agentcask/cask-controller:dev -f build/cask-controller.Dockerfile .
docker build -t agentcask/cask-model-proxy:dev -f build/cask-model-proxy.Dockerfile .
docker build -t agentcask/agent-runtime:dev -f build/agent-runtime.Dockerfile .
kind load docker-image --name agentcask-mvp agentcask/cask-api:dev
kind load docker-image --name agentcask-mvp agentcask/cask-controller:dev
kind load docker-image --name agentcask-mvp agentcask/cask-model-proxy:dev
kind load docker-image --name agentcask-mvp agentcask/agent-runtime:dev
kubectl apply -f config/crd
make kind-deploy
go test ./test/e2e/... -count=1
```

## 6. E2E acceptance

The E2E test must verify:

- `cask-api` ready.
- `cask-model-proxy` ready.
- `cask-controller` ready.
- session creation through `caskctl` or API.
- Agent Pod created.
- terminal connect returns expected output.
- `opencode` is present in the Agent runtime image.
- session delete removes Pod.
- no secret sentinel leaked.

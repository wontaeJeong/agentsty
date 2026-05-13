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

## 3. Manual caskctl testing in local kind

Use this flow when you want to drive `caskctl` yourself instead of running the scripted E2E test.

### 3.1 Deploy the stack

Static kind manifests:

```bash
make build
make kind-up
make kind-load
make kind-deploy
```

Helm chart:

```bash
make build
make kind-up
make kind-load
helm upgrade --install agentcask ./charts/agentcask \
  --namespace agentcask-system \
  --create-namespace
kubectl -n agentcask-system rollout status deploy/cask-api --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-model-proxy --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-controller --timeout=180s
```

Use one deployment path per namespace. If the static manifests already own resources in `agentcask-system`, either keep using `make kind-deploy` or install the chart into separate namespaces through values overrides.

### 3.2 Point caskctl at cask-api

In one terminal:

```bash
kubectl -n agentcask-system port-forward svc/cask-api 18080:8080
```

In another terminal:

```bash
export CASK_API_SERVER=http://127.0.0.1:18080
export CASK_TOKEN=dev-token
```

### 3.3 Create, connect, and delete a session

Use `stub` for deterministic terminal testing:

```bash
./bin/caskctl session create \
  --tool stub \
  --repo https://example.invalid/repo.git \
  --branch main \
  --model default \
  --resource small \
  --isolation default \
  --ttl 30m
```

Use the returned session ID:

```bash
./bin/caskctl session list
./bin/caskctl session get <session-id>
./bin/caskctl session connect <session-id>
```

Inside the connected terminal, run a quick check and exit:

```bash
echo CASK_OK
exit
```

Then clean up:

```bash
./bin/caskctl session delete <session-id>
```

For user-like MVP testing, omit `--tool` or set `--tool opencode`; `opencode` is the default. For terminal gateway assertions, prefer `--tool stub` because it does not depend on model/provider behavior.

## 4. Test cluster setup

Recommended kind cluster name:

```text
agentcask-mvp
```

Recommended namespace:

```text
agentcask-system
agentcask-sessions
```

## 5. RuntimeClass plumbing test

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

## 6. E2E script outline

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

## 7. E2E acceptance

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

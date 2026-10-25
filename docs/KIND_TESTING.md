# kind Testing Guide

## 1. Purpose

kind tests validate the baseline control plane and terminal path locally. They do not certify production readiness, real provider functionality, HA, load capacity, recovery or hostile multitenant isolation. See [Release Criteria](RELEASE_CRITERIA.md) for required additional evidence.

The E2E flow uses the deterministic `stub` tool for terminal assertions, but it also checks that the Agent Pod uses the derived runtime image and contains `opencode`, Git, SSH, and tmux. The runtime extends `ghcr.io/anomalyco/opencode:1.14.48`; the upstream image alone lacks the repository and persistent-terminal tools. E2E port forwards automatically allocate free local ports rather than claiming the manual testing ports 18080/18081.

They do not validate real Kata VM isolation unless the host/kind node is configured with an actual Kata runtime.

## 2. Expected make targets

```bash
make kind-up
make kind-load
make kind-deploy
make kind-test
make kind-down
```

A single command runs the baseline after operator-provided authentication configuration. First set `CASK_OIDC_ISSUER`, `CASK_OIDC_AUDIENCE`, `CASK_OIDC_JWKS_URL` for a reachable HTTPS test IdP and `CASK_E2E_TOKEN` to a signed access token with the API audience and `cask:sessions` scope. Missing values fail preflight (no dev fallback). See the [JWT runbook](RUNBOOK.md#8-jwt-인증-운영-p0-1a). Confirm the target KUBECONFIG/context before running; do not reuse another session's active cluster.

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
  --create-namespace \
  --set-string api.oidc.issuer="$CASK_OIDC_ISSUER" \
  --set-string api.oidc.audience="$CASK_OIDC_AUDIENCE" \
  --set-string api.oidc.jwksURL="$CASK_OIDC_JWKS_URL"
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
# Supply CASK_TOKEN through an approved external JWT issuance process.
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

For user-like baseline testing, omit `--tool` or set `--tool opencode`; `opencode` is the current default, not a permanent runtime priority. For terminal gateway assertions, prefer `--tool stub` because it does not depend on model/provider behavior. `dev-token`/`user:xxx` are rejected in all environments. Port-forwarding is a local operator-controlled test path, not production deployment. Binary presence does not prove checkout/model/file-edit behavior.

## 4. Test cluster setup

Existing kind cluster name (kept for compatibility, not a product scope restriction):

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
- Agent Pod uses `agentcask/agent-runtime:dev`, derived from `ghcr.io/anomalyco/opencode:1.14.48`.
- `opencode`, Git, SSH, and tmux are present in the Agent runtime image.
- session delete removes Pod.
- no secret sentinel leaked.

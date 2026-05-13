# Test Plan: agentcask MVP

## 1. Required commands

```bash
make test
make helm-lint
make helm-template
make kind-test
```

## 2. Unit tests

Required areas:

```text
api request validation
api response mapping
isolation profile mapping
resource profile mapping
secret redaction
controller pod builder
controller status transitions
model proxy token validation
caskctl config loading
caskctl command parsing
```

## 3. Controller tests

Use envtest or fake Kubernetes client for:

- AgentSession -> Pod creation.
- finalizer add/remove.
- status updates.
- default isolation.
- kata isolation mapping.
- unsupported isolation profile.
- RuntimeClass missing.
- Pod env does not include real upstream keys.

## 4. API tests

Use httptest/fake Kubernetes client.

Cases:

- create session success.
- list only user's sessions.
- get session success.
- delete session success.
- reject unknown tool.
- reject unknown isolation profile.
- reject `runtimeClassName`.
- reject secret-looking fields.
- do not expose podName by default.
- no secret values in response.

## 5. Terminal gateway tests

Use fake WebSocket client and fake exec backend.

Cases:

- auth required.
- forbidden for non-owner.
- session not running.
- resize message forwarded.
- binary input forwarded.
- binary output returned.
- disconnect cleans exec stream.

## 6. Model proxy tests

Cases:

- valid session token accepted.
- invalid token rejected.
- upstream API key loaded only server-side.
- Authorization headers redacted in logs.
- request/response does not expose upstream credential.

## 7. caskctl tests

Cases:

- config from file.
- config from env.
- create command sends correct JSON.
- list table output.
- get JSON output.
- delete command.
- connect command opens WebSocket and forwards bytes.
- local terminal state restored on errors where practical.

## 8. Helm chart tests

Minimum checks:

```text
helm lint charts/agentcask
helm template agentcask charts/agentcask
make kind-helm-test
helm install against kind with local dev images
verify cask-api, cask-model-proxy, and cask-controller roll out
run caskctl create/connect/delete through the Helm-installed cask-api
```

## 9. kind E2E tests

Minimum flow:

```text
kind create cluster
build images
kind load docker-image
install CRD
deploy cask-api
deploy cask-controller
run caskctl session create
wait for AgentSession Running
run caskctl session connect with scripted terminal input
verify expected output
run caskctl session delete
verify Pod deleted
```

## 10. Secret leakage tests

The test suite must fail if a known fake upstream key appears in:

```text
AgentSession YAML
Pod env
Pod mounted config
API responses
CLI output
controller logs
cask-api logs
cask-model-proxy logs
```

Use a sentinel value like:

```text
REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK
```

Assert it is visible only to `cask-model-proxy` process/config, never to Agent Pods or user outputs.

## 11. Kata testing

In kind:

- test profile validation and mapping.
- optionally create a fake RuntimeClass for plumbing.
- do not claim real Kata isolation is tested.

On a real Kata cluster:

- create RuntimeClass `kata`.
- label Kata-capable nodes.
- run `isolation.profile=kata`.
- verify Pod has `spec.runtimeClassName=kata`.
- verify Pod starts.

## 12. Helm chart checks

When chart files change, run:

```bash
make helm-lint
make helm-template
make kind-helm-test
```

The rendered manifests must keep `cask-model-proxy` and Agent Pods internal-only, place runtime control-plane components in the Helm release namespace, keep the session namespace configurable, and avoid embedding real upstream model credentials in values, examples, or rendered manifests.

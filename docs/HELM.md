# Helm Deployment Guide

`charts/agentcask` packages the MVP Kubernetes control plane for installable local and cluster deployments.

The chart installs:

- `AgentSession` CRD `agentsessions.agentcask.aidev.samsungds.net`.
- `cask-api` Deployment and ClusterIP Service.
- internal-only `cask-model-proxy` Deployment and ClusterIP Service.
- `cask-controller` Deployment.
- ServiceAccounts, RBAC, session namespace, and Agent Pod egress NetworkPolicy.

The chart does not create per-session Ingress or public Services. End users still access sessions only through `caskctl -> cask-api`.

## Install

```bash
helm upgrade --install agentcask ./charts/agentcask \
  -n agentcask-system \
  --create-namespace
```

The Helm release namespace is the system namespace for `cask-api`, `cask-model-proxy`, and `cask-controller`. Agent sessions use `namespaces.sessions.name`, which defaults to `agentcask-sessions`.

## Upgrade

```bash
helm upgrade --install agentcask ./charts/agentcask \
  -n agentcask-system
```

## Uninstall

```bash
helm uninstall agentcask -n agentcask-system
```

Helm does not delete CRDs installed from `crds/`. Delete CRDs manually only when all `AgentSession` resources are no longer needed.

## CRDs

The chart includes the `AgentSession` CRD in `charts/agentcask/crds/`. Helm installs CRDs before rendering templates on first install, but Helm does not upgrade CRDs automatically.

When the CRD schema changes, apply it explicitly:

```bash
kubectl apply -f charts/agentcask/crds/
```

Use `helm install --skip-crds` only when the platform team manages CRDs separately.

## Key Values

- `api.image.repository`, `api.image.tag`, `api.image.pullPolicy`: `cask-api` image.
- `controller.image.*`: `cask-controller` image.
- `modelProxy.image.*`: `cask-model-proxy` image.
- `agent.image.repository`, `agent.image.tag`: Agent runtime image passed to the controller.
- `namespaces.sessions.name`: namespace for `AgentSession` resources and Agent Pods.
- `sessionToken.existingSecret`: production session-token HMAC Secret reference. If omitted, Helm generates a release-local random Secret.
- `modelProxy.upstream.url`: optional internal model endpoint URL.
- `modelProxy.upstream.existingSecret`: optional upstream credential Secret consumed only by `cask-model-proxy`.
- `networkPolicy.extraEgress`: extra Agent Pod egress rules, such as internal Git service access.
- `runtimeClass.create`: optional dev/test RuntimeClass bootstrap. Production RuntimeClasses should normally be cluster-managed.

## Secrets and Model Access

Do not put real model/API credentials in `values.yaml`, examples, rendered manifests committed to git, `AgentSession` specs/status, or Agent Pod env/mounts.

If the upstream model endpoint requires a credential, create a Kubernetes Secret outside Helm values and reference it:

```bash
kubectl -n agentcask-system create secret generic cask-model-upstream \
  --from-literal=upstreamKey='<REDACTED>'

helm upgrade --install agentcask ./charts/agentcask \
  -n agentcask-system \
  --set modelProxy.upstream.url=https://model.internal.example/v1/chat/completions \
  --set modelProxy.upstream.existingSecret.name=cask-model-upstream \
  --set modelProxy.upstream.existingSecret.key=upstreamKey
```

Only `cask-model-proxy` receives the upstream credential. Agent Pods receive only the internal model proxy URL and a short-lived session proxy token.

## kind Smoke Test

Build and load local images:

```bash
make kind-up
make kind-load
```

Install the chart:

```bash
helm upgrade --install agentcask ./charts/agentcask \
  -n agentcask-system \
  --create-namespace
```

Verify rollout:

```bash
kubectl -n agentcask-system rollout status deploy/cask-api --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-model-proxy --timeout=180s
kubectl -n agentcask-system rollout status deploy/cask-controller --timeout=180s
```

Connect `caskctl`:

```bash
kubectl -n agentcask-system port-forward svc/cask-api 18080:8080
export CASK_API_SERVER=http://127.0.0.1:18080
export CASK_TOKEN=dev-token
./bin/caskctl session create --tool stub --repo https://example.invalid/repo.git --ttl 30m
./bin/caskctl session connect <session-id>
./bin/caskctl session delete <session-id>
```

Use `--tool stub` for deterministic terminal testing. Omit `--tool` for the default `opencode` path.

## Validation

```bash
make helm-lint
make helm-template
make kind-helm-test
```

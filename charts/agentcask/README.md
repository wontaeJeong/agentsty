# agentcask Helm Chart

This chart installs the agentcask MVP control plane:

- `AgentSession` CRD
- `cask-api` REST and WebSocket terminal gateway
- internal-only `cask-model-proxy`
- `cask-controller`
- split ServiceAccounts/RBAC
- session namespace and Agent Pod egress NetworkPolicy

The chart installs runtime components into the Helm release namespace. The session namespace is configurable through `namespaces.sessions.name`.

## Local kind install

Build and load local images first:

```bash
make kind-up
make kind-load
```

Install the chart:

```bash
helm upgrade --install agentcask ./charts/agentcask \
  --namespace agentcask-system \
  --create-namespace
```

Then connect `caskctl` through `cask-api`:

```bash
kubectl -n agentcask-system port-forward svc/cask-api 18080:8080
export CASK_API_SERVER=http://127.0.0.1:18080
export CASK_TOKEN=dev-token
./bin/caskctl session create --tool stub --repo https://example.invalid/repo.git --ttl 30m
```

Use `--tool stub` for deterministic terminal testing. Omit `--tool` or use `--tool opencode` for the MVP user path.

Uninstall the release:

```bash
helm uninstall agentcask -n agentcask-system
```

Helm installs CRDs from `crds/` during the first install. Helm does not upgrade or delete CRDs automatically; apply CRD changes explicitly with:

```bash
kubectl apply -f charts/agentcask/crds/
```

## Key values

- `api.image.*`, `controller.image.*`, `modelProxy.image.*`: control-plane images.
- `agent.image.*`: default Agent runtime image used by `cask-controller`.
- `namespaces.sessions.name`: namespace where `AgentSession` resources and Agent Pods live.
- `sessionToken.existingSecret`: externally managed HMAC token secret for production. If omitted, the chart generates a random release-local Secret.
- `modelProxy.upstream.url`: optional internal/on-prem model endpoint URL.
- `modelProxy.upstream.existingSecret`: optional upstream credential Secret reference consumed only by `cask-model-proxy`.
- `networkPolicy.extraEgress`: additional Agent Pod egress rules, for example to internal Git mirrors.
- `runtimeClass.create`: dev/test RuntimeClass bootstrap. Production RuntimeClasses should normally be cluster-managed.

## Production notes

- Keep `cask-model-proxy` internal-only.
- Expose only `cask-api`; the MVP chart keeps it `ClusterIP` by default for port-forward or platform-managed ingress/gateway integration.
- Do not place real upstream model credentials in committed values files.
- For real upstream credentials, set `modelProxy.upstream.existingSecret.name` and `modelProxy.upstream.existingSecret.key`.
- For production session token signing, set `sessionToken.createSecret=false` and reference an externally managed Secret through `sessionToken.existingSecret`.
- Helm installs CRDs from `crds/` on first install but does not upgrade or delete CRDs. Manage CRD upgrades explicitly or install with `--skip-crds` when a platform team owns CRDs.
- `runtimeClass.create` is disabled by default. The default `handler: runc` is kind plumbing, not real Kata isolation. Production Kata/gVisor RuntimeClasses should be platform-managed.
- `serviceAccounts.agentSession.name` must remain `agent-session` until the controller supports a configurable Agent Pod ServiceAccount.

Safe upstream Secret example:

```bash
kubectl -n agentcask-system create secret generic cask-model-upstream \
  --from-literal=upstreamKey='<REDACTED>'

helm upgrade --install agentcask ./charts/agentcask \
  --namespace agentcask-system \
  --set modelProxy.upstream.url=https://model.internal.example/v1/chat/completions \
  --set modelProxy.upstream.existingSecret.name=cask-model-upstream \
  --set modelProxy.upstream.existingSecret.key=upstreamKey
```

Do not commit real Secret values or rendered Secret manifests.

## Useful checks

```bash
helm lint charts/agentcask
helm template agentcask charts/agentcask --namespace agentcask-system --include-crds >/tmp/agentcask.yaml
make kind-helm-test
```

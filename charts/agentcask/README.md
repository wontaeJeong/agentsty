# agentcask Helm Chart

This chart installs the agentcask MVP control plane:

- `AgentSession` CRD
- `cask-api` REST and WebSocket terminal gateway
- internal-only `cask-model-proxy`
- `cask-controller`
- split ServiceAccounts/RBAC
- session namespace and Agent Pod egress NetworkPolicy

## Local kind install

Build and load local images first:

```bash
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

## Production notes

- Keep `cask-model-proxy` internal-only.
- Expose only `cask-api`, preferably through `api.ingress.enabled=true` with TLS configured by the platform.
- Do not place real upstream model credentials in committed values files.
- For real upstream credentials, set `modelProxy.upstream.existingSecret.name` and `modelProxy.upstream.existingSecret.key`.
- For production session token signing, set `sessionToken.createSecret=false` and reference an externally managed Secret through `sessionToken.existingSecret`.
- Helm installs CRDs from `crds/` on first install but does not upgrade or delete CRDs. Manage CRD upgrades explicitly or install with `--skip-crds` when a platform team owns CRDs.
- `runtimeClass.create` is disabled by default. Enable it only for dev/test bootstrap or when the cluster team wants this chart to own the RuntimeClass.

## Useful checks

```bash
helm lint charts/agentcask
helm template agentcask charts/agentcask --include-crds >/tmp/agentcask.yaml
```

# agentcask Helm Chart

This chart installs the current agentcask baseline control plane, not a certified production deployment:

- `AgentSession` CRD
- `cask-api` REST and WebSocket terminal gateway
- internal-only `cask-model-proxy`
- `cask-controller`
- split ServiceAccounts/RBAC
- session namespace and Agent Pod egress NetworkPolicy

## Local kind install

Build and load the local control-plane and derived runtime images first. The runtime extends the pinned public OpenCode image with Git, SSH, tmux, and the test adapter:

```bash
make kind-load
```

Install the chart after configuring a real HTTPS test IdP (API audience and `cask:sessions` scope). Missing issuer/audience/JWKS values fail rendering; no dev authentication fallback exists:

```bash
helm upgrade --install agentcask ./charts/agentcask \
  --namespace agentcask-system \
  --create-namespace \
  --set-string api.oidc.issuer="$CASK_OIDC_ISSUER" \
  --set-string api.oidc.audience="$CASK_OIDC_AUDIENCE" \
  --set-string api.oidc.jwksURL="$CASK_OIDC_JWKS_URL"
```

Then connect `caskctl` through `cask-api`:

```bash
kubectl -n agentcask-system port-forward svc/cask-api 18080:8080
export CASK_API_SERVER=http://127.0.0.1:18080
# Supply CASK_TOKEN through an approved external JWT issuance process.
./bin/caskctl session create --tool stub --repo https://example.invalid/repo.git --ttl 30m
```

Use `--tool stub` for deterministic terminal testing. Omit `--tool` or use `--tool opencode` for the current default user path. Binary presence and stub success are not real provider integration evidence. The local images and port-forwarding above are development examples only. `dev-token` and `user:xxx` are rejected, including locally. CLI device login/refresh and immediate JWT revocation are not implemented; see ADR-007 and the runbook.

## Production notes

- Keep `cask-model-proxy` internal-only.
- The current chart exposes `cask-api`; prefer `api.ingress.enabled=true` with TLS configured by the platform. Additional product UI/gateway services are permitted through an ADR preserving authentication/authorization and private Agent Pods. This does not make the internal model proxy public.
- Do not place real upstream model credentials in committed values files.
- For real upstream credentials, set `modelProxy.upstream.existingSecret.name` and `modelProxy.upstream.existingSecret.key`.
- For production session token signing, set `sessionToken.createSecret=false` and reference an externally managed Secret through `sessionToken.existingSecret`.
- Helm installs CRDs from `crds/` on first install but does not upgrade or delete CRDs. Manage CRD upgrades explicitly or install with `--skip-crds` when a platform team owns CRDs.
- `runtimeClass.create` is disabled by default. Enable it only for dev/test bootstrap or when the cluster team wants this chart to own the RuntimeClass.

These settings alone do not satisfy production requirements. Validate identity, least-privilege RBAC, actual network/runtime/data isolation, recovery, capacity, observability and reproducible upgrades in the target environment under [Release Criteria](../../docs/RELEASE_CRITERIA.md). See [Production Roadmap](../../docs/PRODUCTION_ROADMAP.md) for follow-up work; no HA, durable session recovery or real Kata guarantee is asserted by installing the chart.

## Useful checks

```bash
make helm-lint
make helm-template
go test ./test/helm -count=1
```

The make targets use `ci/oidc-values.yaml`, a render-only fixture with non-working IdP URLs. It must never be installed as a functional deployment. Override `HELM_VALUES` for your actual operator-owned configuration. Successful rendering does not validate that issuer/JWKS are reachable or that an IdP issues usable access tokens.

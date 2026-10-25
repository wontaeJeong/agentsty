# Runbook: agentcask Baseline

These are existing operator diagnostics for the current topology, not a complete production operations guide. Kubernetes commands are for authorized operators with least-privilege access, not end-user product access. Never copy secrets or unredacted terminal/model bodies into diagnostic output or incident reports.

## 1. Check system pods

```bash
kubectl -n agentcask-system get pods
```

Expected:

```text
cask-api
cask-model-proxy
cask-controller
```

## 2. Check CRD

```bash
kubectl get crd agentsessions.agentcask.aidev.samsungds.net
```

## 3. List sessions

```bash
kubectl -n agentcask-sessions get agentsessions
```

## 4. Inspect a failed session

```bash
kubectl -n agentcask-sessions get agentsession <name> -o yaml
```

Check:

```text
status.phase
status.reason
status.message
```

## 5. Common failures

### RuntimeClassNotFound

Cause:

```text
isolation.profile maps to a RuntimeClass that does not exist
```

Fix:

```bash
kubectl get runtimeclass
```

Install the runtime or change `isolationProfiles`.

### PodUnschedulable

Cause:

```text
nodeSelector/tolerations do not match available nodes
```

Fix:

```bash
kubectl describe pod <pod>
kubectl get nodes --show-labels
```

### TerminalNotReady

Cause:

```text
Pod not ready, container missing, or pods/exec permission missing
```

Fix:

```bash
kubectl auth can-i create pods/exec --as system:serviceaccount:agentcask-system:cask-api -n agentcask-sessions
```

### SecretLeakTestFailed

Cause:

```text
fake upstream key appeared in Pod/CR/API/log output
```

Fix:

- remove real/sentinel key from Agent Pod env
- ensure only proxy token is injected
- update redaction middleware

### ModelProxyUnauthorized

Cause:

```text
session proxy token is expired, revoked, invalid, or no longer maps to a live AgentSession
```

Fix:

```bash
kubectl -n agentcask-system logs deploy/cask-model-proxy
kubectl -n agentcask-sessions get agentsession <name> -o yaml
```

## 6. Force cleanup

```bash
kubectl -n agentcask-sessions delete agentsession <name>
```

If finalizer is stuck during development only:

```bash
kubectl -n agentcask-sessions patch agentsession <name> \
  --type=json \
  -p='[{"op":"remove","path":"/metadata/finalizers"}]'
```

Use finalizer removal only for dev/test recovery.

## 7. Production operations gaps and release prerequisites

Before production use, supply and exercise deployment-specific procedures for identity/permission incidents, key/token rotation and revocation, dependency outages, node/component failure, cleanup failures, storage retention and backup/restore where state is persistent, upgrade/migration/rollback, alert response and capacity/performance management. Define recovery-time/data-loss objectives and demonstrate recovery against them.

These procedures and guarantees are not implemented by this runbook update. Record operator ownership, safe diagnostics, monitoring signals, exact supported configuration and drill evidence in the release record. Do not remove finalizers in production without a reviewed recovery procedure that checks resource/data cleanup and ownership. See [Release Criteria](RELEASE_CRITERIA.md) and [Production Roadmap](PRODUCTION_ROADMAP.md).

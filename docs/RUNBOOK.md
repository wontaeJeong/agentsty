# Runbook: agentcask MVP

## 1. Check system pods

```bash
kubectl -n agentcask-system get pods
```

Expected:

```text
cask-api
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

# Controller Design: cask-controller MVP

## 1. Reconcile overview

```text
Watch AgentSession
  -> validate/decode desired state
  -> ensure finalizer
  -> resolve isolation profile
  -> resolve resource profile
  -> ensure proxy token/non-secret config
  -> create/update Agent Pod
  -> update status
```

## 2. Owned resources

For each AgentSession, the controller may create:

```text
Pod
PVC optional
ConfigMap optional
Secret containing short-lived proxy token optional
NetworkPolicy
```

The controller must set owner references where appropriate.

## 3. Pod creation

MVP Pod model:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: agent-session-sess-abc123
  namespace: agentcask-sessions
spec:
  restartPolicy: Never
  serviceAccountName: agent-session
  containers:
    - name: agent
      image: agent-runtime:<fixed-version>
      command: ["sleep", "infinity"]
      stdin: true
      tty: true
```

`cask-api` connects later using `pods/exec`.

## 4. tmux model

On terminal connection, `cask-api` should execute a command equivalent to:

```bash
tmux new-session -A -s agent '<tool command>'
```

or attach to an existing session.

This allows reconnect behavior to be implemented without making the Agent Pod main process the TUI.

## 5. isolationProfiles application

Controller config:

```yaml
isolationProfiles:
  default:
    runtimeClassName: ""
  kata:
    runtimeClassName: kata
    nodeSelector:
      agentcask.aidev.samsungds.net/kata: "true"
    tolerations: []
```

Reconcile logic:

```text
profile = session.spec.isolation.profile

if profile == default:
  omit pod.spec.runtimeClassName

if profile == kata:
  check RuntimeClass exists
  set pod.spec.runtimeClassName
  apply nodeSelector/tolerations
```

If profile is invalid:

```yaml
status:
  phase: Failed
  reason: UnsupportedIsolationProfile
```

If RuntimeClass is missing:

```yaml
status:
  phase: Failed
  reason: RuntimeClassNotFound
```

## 6. Model proxy injection

Controller may inject:

```text
CASK_MODEL_BASE_URL
CASK_SESSION_TOKEN
OPENAI_BASE_URL
ANTHROPIC_BASE_URL
OPENAI_API_KEY=<short-lived proxy token only if tool requires it>
ANTHROPIC_API_KEY=<short-lived proxy token only if tool requires it>
```

The values named `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` must never be real upstream keys.

## 7. Status update rules

Set:

```yaml
status:
  phase: Provisioning
```

after starting resource creation.

Set:

```yaml
status:
  phase: Running
  podName: ...
  terminalReady: true
```

when Pod is ready enough for exec.

Set:

```yaml
status:
  phase: Failed
  reason: ...
  message: ...
```

for unrecoverable errors.

Messages must be redacted.

## 8. TTL cleanup

If `createdAt + ttlSeconds < now`, controller should:

1. mark session `Expired` or delete it depending on MVP policy.
2. delete owned Pod/PVC/Secret/ConfigMap.
3. close terminal indirectly by Pod deletion.

## 9. Forbidden controller behavior

The controller must not:

- create per-session Ingress by default
- expose Pod via NodePort
- mount upstream model credentials into Agent Pod
- allow privileged containers
- allow hostPath
- allow hostNetwork
- give Agent Pod broad Kubernetes API permissions

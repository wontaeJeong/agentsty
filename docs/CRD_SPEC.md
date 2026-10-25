# CRD Spec: AgentSession

## 1. API group

```text
agentcask.aidev.samsungds.net
```

## 2. Kind

```text
AgentSession
```

## 3. Resource

```text
agentsessions.agentcask.aidev.samsungds.net
```

## 4. Version

The current version is `v1alpha1`; the production policy does not promote it to a stable version. Future schema/version changes require compatibility, migration/conversion and rollback analysis through an ADR.

## 5. Example

```yaml
apiVersion: agentcask.aidev.samsungds.net/v1alpha1
kind: AgentSession
metadata:
  name: sess-abc123
  namespace: agentcask-sessions
  labels:
    agentcask.aidev.samsungds.net/user-id: user-123
spec:
  userId: user-123
  tool: opencode
  repo:
    url: https://gitlab.example.com/team/project.git
    branch: main
  modelRef: default
  resourceProfile: small
  isolation:
    profile: default
  ttlSeconds: 7200
status:
  phase: Running
  reason: ""
  message: ""
  podName: agent-session-sess-abc123
  containerName: agent
  terminalReady: true
  createdAt: "2026-05-12T00:00:00Z"
  expiresAt: "2026-05-12T02:00:00Z"
```

## 6. Spec fields

### userId

Internal owner identity resolved by `cask-api`.

Do not trust user-submitted `userId` from public API requests.

### tool

Baseline design values (not proof that every runtime integration is implemented):

```text
opencode
claude-code
codex
openclaw
hermes
stub
```

Currently `opencode` is the default real tool. Other runtimes may be prioritized by product requirements, with explicit implementation and real integration tests. `stub` remains a deterministic test adapter, not evidence of agent functionality.

### repo

Fields:

```yaml
repo:
  url: string
  branch: string
```

Never store Git credentials directly in this object; future credential integrations must preserve the secret boundary.

### modelRef

Reference to a server-side model configuration.

Example:

```yaml
modelRef: default
```

This is not a secret.

### resourceProfile

Baseline values (extend only through validated, compatible contract changes):

```text
small
medium
large
```

The controller maps profiles to CPU/memory/ephemeral-storage.

### isolation.profile

Baseline values (new isolation profiles are permitted with threat-model and runtime validation):

```text
default
kata
```

Rules:

- `default` means no runtimeClassName.
- `kata` maps through controller config to `runtimeClassName`.
- Do not include raw `runtimeClassName` in AgentSession spec.

### ttlSeconds

Maximum session lifetime.

Controller must delete or mark expired sessions after TTL.

## 7. Status fields

### phase

Allowed values:

```text
Pending
Provisioning
Running
Failed
Terminating
Expired
Succeeded
```

### reason

Machine-readable reason.

Examples:

```text
UnsupportedTool
UnsupportedIsolationProfile
RuntimeClassNotFound
PodCreateFailed
PodUnschedulable
TerminalNotReady
Expired
```

### message

Human-readable explanation.

Must not contain secrets.

### podName

Internal Pod name. `cask-api` may use it internally. Normal user responses should avoid exposing it unless required.

### terminalReady

Whether terminal connection is expected to work.

## 8. Finalizer

Use a finalizer for cleanup:

```text
agentcask.aidev.samsungds.net/finalizer
```

Controller removes owned resources, then removes finalizer.

## 9. Validation requirements

CRD schema should reject:

- empty tool
- empty resourceProfile
- empty isolation.profile
- unsupported ttl ranges if possible
- unknown enum values where practical

API server should perform stricter validation before creating CRs.

## 10. Secret prohibition

AgentSession must never contain:

- API keys
- model provider secrets
- mTLS private keys
- Git passwords
- personal access tokens
- kubeconfig

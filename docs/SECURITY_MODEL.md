# Security Model: MVP

## 1. Primary security boundary

Agent Pods execute user-influenced tools. Treat them as untrusted workloads.

The security boundary must be:

```text
user -> cask-api -> Kubernetes API -> isolated Agent Pod
```

Users never directly access:

- Kubernetes API
- Agent Pod IP
- per-session Ingress
- raw kubeconfig
- upstream model secrets

## 2. API key leakage prevention

Real model/API keys must never be placed in:

```text
AgentSession.spec
AgentSession.status
caskctl config/output
API request bodies
API responses
Agent Pod env vars
Agent Pod volumes
terminal output
controller logs
cask-api logs
test fixtures committed to git
```

Only `cask-api` may hold upstream credentials.

## 3. Model proxy pattern

MVP model access:

```text
Agent Pod
  -> cask-api internal model proxy
  -> on-prem model endpoint
```

The Agent Pod receives one of:

- short-lived session proxy token
- projected service account token
- internal-only auth material scoped to the session

The Agent Pod does not receive real upstream credentials.

## 4. Tool compatibility

Some CLIs require variables like:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

If unavoidable, those variables must contain only a short-lived proxy token accepted by `cask-api`, not a real provider key.

The proxy token must be:

- session-scoped
- revocable
- TTL-bound
- useless against upstream model endpoints directly

## 5. Kubernetes RBAC

### cask-api ServiceAccount

Needs:

```text
get/list/create/delete AgentSession
get AgentSession/status
get pods
create pods/exec
```

Avoid granting broad Pod create/delete to `cask-api`.

### cask-controller ServiceAccount

Needs:

```text
watch/list/get AgentSession
update AgentSession/status
create/update/delete Pods
create/update/delete ConfigMaps/Secrets/PVCs/NetworkPolicies as needed
get RuntimeClass
```

### Agent Pod ServiceAccount

Should have minimal or no Kubernetes API permissions.

Do not mount a powerful service account into Agent Pods.

## 6. Pod security defaults

Agent Pods must avoid:

```text
privileged: true
hostNetwork: true
hostPID: true
hostIPC: true
hostPath volumes
Docker socket mounts
broad Linux capabilities
```

Prefer:

```text
runAsNonRoot: true
allowPrivilegeEscalation: false
readOnlyRootFilesystem where compatible
seccompProfile: RuntimeDefault
capabilities.drop: ["ALL"]
```

## 7. Network policy

MVP should aim to restrict Agent Pod egress to:

- `cask-api` model proxy
- Git endpoint if needed
- package mirrors if explicitly allowed

Agent Pods should not be able to reach arbitrary internal services by default.

## 8. Logging

Logs must redact:

```text
Authorization
Cookie
Set-Cookie
X-API-Key
OPENAI_API_KEY
ANTHROPIC_API_KEY
CASK_SESSION_TOKEN
```

Do not log full request bodies for model proxy calls.

## 9. Tests required

Add negative tests proving:

- AgentSession never contains API key fields.
- API create session rejects secret-looking fields.
- Pod env does not contain real upstream key values.
- API responses do not echo secrets.
- logs redact sensitive header names/values.

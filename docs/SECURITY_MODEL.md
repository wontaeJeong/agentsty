# Security Model

These are mandatory security requirements, not a claim that every deployment already enforces them. Verify enforcement through [Release Criteria](RELEASE_CRITERIA.md). Architecture flexibility never waives these boundaries.

## 1. Primary security boundary

Agent Pods execute user-influenced tools. Treat them as untrusted workloads.

The security boundary must be:

```text
user -> cask-api -> Kubernetes API -> isolated Agent Pod
```

This is the current access path. Additional authenticated product gateways or portals may be introduced by ADR without granting users direct Kubernetes/Pod access. Authenticate and authorize each user/session operation, including terminal and model access. Enforce ownership/tenant boundaries, permission expiry/revocation and deny-by-default behavior; do not trust a request-supplied identity. Untrusted code must execute with isolation matched to its threat model, not unrestricted host authority.

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
cask-model-proxy logs
test fixtures committed to git
```

Only `cask-model-proxy` may hold upstream credentials.

## 3. Model proxy pattern

Credential-isolated model access:

```text
Agent Pod
  -> cask-model-proxy internal model proxy
  -> on-prem model endpoint
```

The Agent Pod receives one of:

- short-lived session proxy token accepted by `cask-model-proxy`
- projected service account token
- internal-only auth material scoped to the session

The Agent Pod does not receive real upstream credentials.

## 4. Tool compatibility

Some CLIs require variables like:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

If unavoidable, those variables must contain only a short-lived proxy token accepted by `cask-model-proxy`, not a real provider key.

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

### cask-model-proxy ServiceAccount

Needs:

```text
get/list AgentSession
get AgentSession/status
```

It must not create AgentSessions or Pods.

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

Must have only explicitly justified minimal Kubernetes API permissions, preferably none.

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

Production must enforce private-by-default networking and an explicit egress allow-list for Agent Pods, such as:

- `cask-model-proxy` model proxy
- Git endpoint if needed
- package mirrors if explicitly allowed

Agent Pods should not be able to reach arbitrary internal services by default.

Enforce resource and data separation across users/sessions, including storage ownership, cleanup/retention, network reachability and shared-service authorization. Choose isolation strength by threat model; omitting runtimeClassName or passing fake RuntimeClass plumbing is not proof of safe hostile multitenant execution. Validate actual enforcement in the target cluster.

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

Also verify cross-user/session/tenant denial, expired/revoked credentials, least-privilege RBAC, actual network policy and runtime isolation, resource contention and cleanup/recovery. Test doubles alone cannot validate these deployment boundaries.

## 10. Production security evolution

Vault, SPIFFE, External Secrets, OIDC and other reviewed integrations are allowed, not excluded by historical scope. Specific technologies are optional; required security outcomes are not. Document token/key rotation, revocation, incident response and dependency-failure behavior. Only the internal `cask-model-proxy` credential boundary may hold upstream model credentials; new gateway capabilities must not distribute those keys to Agent Pods or public-facing components.

# PRD: agentcask

## 1. Summary

`agentcask` is a Kubernetes-native platform for running interactive coding agents in isolated Pod sessions.

The current development baseline provides a CLI workflow:

```text
caskctl
  -> cask-api
  -> AgentSession CRD
  -> cask-controller
  -> Agent Pod
  -> cask-model-proxy
  -> cask-api WebSocket terminal gateway
  -> caskctl terminal session
```

The product may support multiple TUI-based tools, including:

- Claude Code
- Codex CLI
- opencode
- OpenClaw
- Hermes

Currently `caskctl` is the client and no Web UI is implemented. Web UI and administration portals are allowed product extensions, not prohibited scope. The list above is a target compatibility set, not a claim that every integration is implemented or validated. New runtime priorities follow user requirements and security/operational evidence rather than a permanent OpenCode-first policy.

This PRD owns product purpose and user workflows. [Production requirements](docs/PRODUCTION_REQUIREMENTS.md) define target capabilities, the [roadmap](docs/PRODUCTION_ROADMAP.md) sequences follow-up work, and [release criteria](docs/RELEASE_CRITERIA.md) define completion evidence. This policy transition does not certify the current implementation for production.

## 2. Goals

The existing baseline is organized around:

1. A working `cask-api` server.
2. A working `cask-controller`.
3. A Kubernetes `AgentSession` CRD.
4. A `caskctl` CLI.
5. WebSocket terminal access through `cask-api`.
6. Optional runtime isolation via `isolationProfiles`.
7. A secure model access pattern that prevents real API key leakage.
8. Unit, integration, and kind-based E2E tests.
9. Documentation and prompts suitable for Codex, Claude Code, and opencode.

## 3. Scope and permanent security boundaries

Production development is not capped at the initial feature set. Portals, organization/permission management, quota/billing, advanced model gateways, Vault/SPIFFE/External Secrets, persistent workspaces, session recovery, HA and horizontal scaling may be designed and introduced based on requirements. They are not implemented by this policy change and specific technologies are not compulsory.

Retained security boundaries:

- No direct end-user Kubernetes API or Agent Pod access through product clients; never grant unrestricted Kubernetes access.
- No real upstream provider/model API keys inside Agent Pods or user-visible artifacts.
- No per-session public Service or Ingress by default; use authenticated, authorized product gateways and private networks.
- Least-privilege RBAC and isolation for untrusted code, resources and data across users/sessions.

This change does not implement large product features or change runtime contracts. Structural changes require an ADR, threat modeling and API/CRD compatibility analysis.

## 4. Core components

### 4.1 cask-api

`cask-api` is the currently externally exposed server. Approved UI or gateway services may be added without exposing Agent Pods or the internal model proxy directly.

Responsibilities:

- REST API for sessions.
- WebSocket terminal gateway.
- User input validation.
- AgentSession CR creation/read/delete.
- Session ownership checks.
- Redaction of secrets in logs and errors.

### 4.1.1 cask-model-proxy

`cask-model-proxy` is internal-only and is not externally exposed.

Responsibilities:

- Internal model proxy, extensible for provider/model requirements without exposing upstream credentials.
- Session proxy token validation.
- Upstream model credential storage.
- Redaction of secrets in logs and errors.

### 4.2 cask-controller

`cask-controller` watches `AgentSession` resources.

Responsibilities:

- Reconcile AgentSession -> Agent Pod.
- Apply `isolationProfiles`.
- Create optional PVC/ConfigMap/Secret resources.
- Inject only non-real proxy credentials into Agent Pods.
- Update AgentSession status.
- Clean up resources after delete/TTL.

### 4.3 AgentSession CRD

The CRD is the internal orchestration API.

API group:

```text
agentcask.aidev.samsungds.net
```

Primary resource:

```text
agentsessions.agentcask.aidev.samsungds.net
```

The CRD must not contain real model/API keys.

### 4.4 caskctl

`caskctl` is the CLI used by end users.

Current baseline commands:

```bash
caskctl session create
caskctl session list
caskctl session get <session-id>
caskctl session connect <session-id>
caskctl session delete <session-id>
```

`caskctl session connect` opens a WebSocket terminal connection to `cask-api`.

### 4.5 Agent runtime image

The current baseline uses one runtime image containing shell tools, `opencode`, and a test adapter command. Multiple runtime images/adapters are permitted when tested and supported explicitly.

The runtime image should support:

- `tmux`
- shell
- git
- `opencode` as the primary agent CLI
- a deterministic test command for E2E

For early kind tests, a stub TUI command is acceptable.

Currently `opencode` is the default agent CLI. This is a current implementation choice, not a permanent priority over other agents. The `stub` tool remains only a deterministic test adapter; it does not demonstrate real agent/provider integration.

## 5. User workflows

### 5.1 Create a session

```bash
caskctl session create \
  --tool opencode \
  --repo https://gitlab.example.com/team/project.git \
  --branch main \
  --model default \
  --isolation default
```

Expected result:

```text
session created: sess-abc123
status: Pending
```

### 5.2 Wait/list sessions

```bash
caskctl session list
```

Expected result:

```text
ID            TOOL       STATUS    ISOLATION    AGE
sess-abc123   opencode   Running   default      34s
```

### 5.3 Connect to terminal

```bash
caskctl session connect sess-abc123
```

Expected result:

- local terminal attaches to the session through WebSocket.
- user never receives kubeconfig.
- user never accesses the Pod directly.

### 5.4 Delete a session

```bash
caskctl session delete sess-abc123
```

Expected result:

- AgentSession is deleted.
- controller removes owned resources.
- Pod disappears.
- terminal connection is closed if active.

## 6. Isolation profiles

Use an `isolationProfiles` structure to preserve a stable user-facing isolation contract. New profiles and dynamic policies may be introduced through compatible, validated changes.

User-facing input:

```yaml
isolation:
  profile: kata
```

Controller mapping:

```yaml
isolationProfiles:
  default:
    runtimeClassName: ""
  kata:
    runtimeClassName: kata
    nodeSelector:
      agentcask.aidev.samsungds.net/kata: "true"
```

Rules:

- Users must not submit arbitrary `runtimeClassName`.
- API accepts only allow-listed isolation profiles.
- Controller maps profile -> runtimeClassName/nodeSelector/tolerations.
- Missing RuntimeClass should mark the session `Failed` with reason `RuntimeClassNotFound`.

## 7. API key leakage prevention

This is a permanent security requirement, independent of delivery scope.

Real model/API keys must never appear in:

- `AgentSession.spec`
- `AgentSession.status`
- user API request bodies
- user API responses
- Agent Pod env vars
- Agent Pod mounted files
- terminal output
- controller logs
- cask-api logs
- caskctl output

Preserve this credential isolation pattern as the product evolves:

```text
Agent Pod
  -> cask-model-proxy internal model proxy
  -> on-prem model endpoint
```

Only `cask-model-proxy` may hold upstream model credentials.

Agent Pods may receive:

- internal model proxy URL
- short-lived session proxy token
- projected service account token

Agent Pods must not receive:

- real `OPENAI_API_KEY`
- real `ANTHROPIC_API_KEY`
- real on-prem model endpoint key
- mTLS private keys for upstream model providers

If a CLI requires an environment variable named like `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, the value must be a short-lived proxy token, never the real upstream key.

## 8. Regression baseline and production acceptance

The following initial regression checks remain useful but are not a product Definition of Done. Production releases and new features must additionally meet [Release Criteria](docs/RELEASE_CRITERIA.md). A test skip or fake runtime is not real isolation evidence.

1. `make test` passes.
2. `make kind-test` passes on a local kind cluster.
3. CRDs install successfully.
4. `cask-api` starts and exposes health endpoints.
5. `cask-model-proxy` starts internally and exposes health endpoints.
6. `cask-controller` starts and reconciles AgentSession.
7. `caskctl session create` creates an AgentSession.
8. Controller creates a corresponding Agent Pod.
9. `caskctl session connect` attaches to the Pod through `cask-api` WebSocket terminal.
10. `caskctl session delete` deletes the session and owned Pod.
11. `isolation.profile=default` works in kind.
12. `isolation.profile=kata` mapping is tested in kind with a fake/plumbing RuntimeClass or skipped unless available.
13. No test exposes real model/API keys to AgentSession, Pod env, API response, terminal output, CLI output, or logs.

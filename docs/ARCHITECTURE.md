# Architecture: agentcask MVP

## 1. High-level structure

```text
User terminal
  -> caskctl
  -> HTTPS/WSS
  -> cask-api
       - REST session API
       - WebSocket terminal gateway
       - minimal model proxy
  -> Kubernetes API
  -> AgentSession CRD
  -> cask-controller
  -> Agent Pod
```

Only `cask-api` is externally exposed.

## 2. Component responsibilities

### caskctl

End-user CLI.

Responsibilities:

- Authenticate to `cask-api`.
- Create sessions.
- List sessions.
- Show session details.
- Connect to terminal via WebSocket.
- Delete sessions.

`caskctl` must not use kubeconfig or call Kubernetes API.

### cask-api

External API server.

Responsibilities:

- Validate client requests.
- Create/read/delete `AgentSession` resources.
- Check session ownership.
- Open WebSocket terminal sessions.
- Bridge terminal stream to Kubernetes `pods/exec`.
- Hold upstream model provider credentials.
- Proxy model calls from Agent Pods to the on-prem model endpoint.
- Redact sensitive values from logs/errors.

### cask-controller

Kubernetes controller.

Responsibilities:

- Watch `AgentSession`.
- Create Agent Pod.
- Apply resource profile.
- Apply isolation profile.
- Inject only proxy URL/token, not real model keys.
- Update status.
- Cleanup on deletion/TTL.

### Agent Pod

Per-session execution environment.

Responsibilities:

- Run a shell/tmux/agent CLI session.
- Hold workspace files.
- Call model through internal `cask-api` model proxy.
- Never hold real upstream provider credentials.

## 3. Data flow: session creation

```text
caskctl session create
  -> POST /api/v1/sessions
  -> cask-api validates request
  -> cask-api creates AgentSession
  -> cask-controller reconciles
  -> Agent Pod created
  -> status.phase=Running
```

## 4. Data flow: terminal connect

```text
caskctl session connect sess-abc
  -> WSS /api/v1/sessions/sess-abc/terminal
  -> cask-api validates ownership
  -> cask-api reads AgentSession.status.podName
  -> cask-api opens Kubernetes pods/exec
  -> command: tmux attach -t agent || tmux new -s agent
  -> byte stream bridged to local terminal
```

## 5. Data flow: model access

```text
Agent CLI inside Pod
  -> internal model proxy URL
  -> cask-api model proxy
  -> on-prem model endpoint
```

Real upstream credentials remain inside `cask-api` only.

## 6. Kubernetes resources

System resources:

```text
Namespace: agentcask-system
Deployment: cask-api
Service: cask-api
Ingress: cask-api
Deployment: cask-controller
ServiceAccount/RBAC
ConfigMap: isolationProfiles
Secret: upstream model credentials
CRD: AgentSession
```

Session resources:

```text
AgentSession
Agent Pod
optional PVC
optional ConfigMap
optional short-lived proxy-token Secret
NetworkPolicy
```

No per-session Ingress is created by default.

## 7. MVP deployment boundary

For MVP, `cask-api` contains three logical modules:

```text
REST API
Terminal Gateway
Model Proxy
```

They may later be split into separate services, but do not split them for MVP unless required by implementation constraints.

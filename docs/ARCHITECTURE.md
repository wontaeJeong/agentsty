# Architecture: agentcask MVP

## 1. High-level structure

```text
User terminal
  -> caskctl
  -> HTTPS/WSS
  -> cask-api
       - REST session API
       - WebSocket terminal gateway
  -> Kubernetes API
  -> AgentSession CRD
  -> cask-controller
  -> Agent Pod
  -> cask-model-proxy
       - minimal model proxy
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
- Redact sensitive values from logs/errors.

### cask-model-proxy

Internal-only model proxy.

Responsibilities:

- Hold upstream model provider credentials.
- Validate session-scoped proxy tokens.
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
- Call model through internal `cask-model-proxy` service.
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
  -> cask-model-proxy
  -> on-prem model endpoint
```

Real upstream credentials remain inside `cask-model-proxy` only.

## 6. Kubernetes resources

System resources:

```text
Namespace: agentcask-system
Deployment: cask-api
Service: cask-api
Ingress: cask-api
Deployment: cask-model-proxy
Service: cask-model-proxy (ClusterIP internal only)
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

For MVP, `cask-api` contains two logical modules:

```text
REST API
Terminal Gateway
```

The minimal Model Proxy is split into `cask-model-proxy` so upstream credentials are isolated in an internal-only component while `cask-api` remains the only externally exposed runtime service.

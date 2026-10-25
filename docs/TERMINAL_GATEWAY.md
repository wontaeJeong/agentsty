# Terminal Gateway: Current Design and Evolution

The terminal gateway is currently implemented inside `cask-api`. A separate gateway service is permitted with an ADR addressing authentication/authorization propagation, routing, failure/reconnect behavior, observability and API/protocol compatibility. This document does not impose permanent co-location or certify production readiness.

## 1. Endpoint

```text
WSS /api/v1/sessions/{sessionId}/terminal
```

## 2. Connection flow

```text
client connects
  -> authenticate
  -> authorize session ownership
  -> read AgentSession
  -> verify status.terminalReady
  -> resolve podName/containerName
  -> open Kubernetes pods/exec stream
  -> bridge bytes between WebSocket and exec stream
```

## 3. Kubernetes exec command

Current baseline command for real user sessions:

```bash
tmux new-session -A -s agent '<agent command>'
```

Primary example:

```bash
tmux new-session -A -s agent 'opencode'
```

Other tool mappings may use the same pattern when supported by the runtime image:

```bash
tmux new-session -A -s agent 'claude'
tmux new-session -A -s agent 'codex'
tmux new-session -A -s agent 'bash'
```

For deterministic tests, keep using the stub adapter instead of launching an interactive model-backed tool:

```bash
tmux new-session -A -s agent 'bash'
```

or:

```bash
tmux new-session -A -s agent '/usr/local/bin/cask-stub-tui'
```

## 4. WebSocket frame protocol

Binary frames:

```text
raw terminal bytes
```

JSON text frames:

```json
{
  "type": "resize",
  "cols": 120,
  "rows": 40
}
```

Optional control message:

```json
{
  "type": "ping"
}
```

## 5. Resize handling

The terminal gateway must pass resize events to the Kubernetes exec stream.

Invalid resize values must be ignored or rejected.

## 6. Authorization rule

The client supplies only:

```text
sessionId
```

The client must not supply:

```text
namespace
podName
containerName
command
runtimeClassName
```

These values are resolved internally from AgentSession and server-side config.

## 7. Disconnect behavior

Baseline behavior/design:

- WebSocket disconnect closes the active exec stream.
- tmux session may remain alive inside Pod.
- reconnect attaches to the same tmux session if Pod still exists.

## 8. Audit/logging

Required logging policy:

- log connection open/close metadata
- log sessionId/userId/phase
- do not log raw terminal input/output by default
- never log tokens or API keys

Terminal I/O capture is permitted only with explicit authorization, retention, privacy and secret-handling controls; raw capture is disabled by default. Production acceptance additionally requires real reconnect/disconnect, session deletion/expiry, backpressure/resource limits and dependency-failure validation; tmux persistence inside a live Pod is not cross-Pod session recovery. See [Release Criteria](RELEASE_CRITERIA.md).

## 9. Failure cases

Return clean errors for:

```text
session not found
forbidden
session not running
terminal not ready
pod not found
exec permission denied
connection timeout
```

Do not include Kubernetes internal stack traces in user-facing errors.

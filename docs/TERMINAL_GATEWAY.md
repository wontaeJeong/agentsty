# Terminal Gateway: MVP Design

The terminal gateway is implemented inside `cask-api` for MVP.

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

Recommended MVP command:

```bash
tmux new-session -A -s agent '<agent command>'
```

Examples:

```bash
tmux new-session -A -s agent 'opencode'
tmux new-session -A -s agent 'claude'
tmux new-session -A -s agent 'codex'
tmux new-session -A -s agent 'bash'
```

For deterministic tests:

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

MVP behavior:

- WebSocket disconnect closes the active exec stream.
- tmux session may remain alive inside Pod.
- reconnect attaches to the same tmux session if Pod still exists.

## 8. Audit/logging

For MVP:

- log connection open/close metadata
- log sessionId/userId/phase
- do not log raw terminal input/output by default
- never log tokens or API keys

Terminal I/O capture can be added later with explicit policy controls.

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

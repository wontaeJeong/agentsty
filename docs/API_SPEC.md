# API Spec: cask-api MVP

## 1. Base path

```text
/api/v1
```

## 2. Authentication

MVP may start with a simple bearer token or mock user identity for local testing.

All handlers must be designed to receive a resolved user identity:

```text
userId
tenantId optional
```

Do not pass userId from the request body as a trusted value.

## 3. Create session

```http
POST /api/v1/sessions
Content-Type: application/json
Authorization: Bearer <token>
```

Request:

```json
{
  "tool": "opencode",
  "repoUrl": "https://gitlab.example.com/team/project.git",
  "branch": "main",
  "modelRef": "default",
  "resourceProfile": "small",
  "isolationProfile": "default",
  "ttlSeconds": 7200
}
```

Response:

```json
{
  "id": "sess-abc123",
  "phase": "Pending",
  "tool": "opencode",
  "modelRef": "default",
  "resourceProfile": "small",
  "isolationProfile": "default",
  "createdAt": "2026-05-12T00:00:00Z",
  "terminalUrl": "/api/v1/sessions/sess-abc123/terminal"
}
```

Rules:

- `tool` must be allow-listed.
- `modelRef` must be allow-listed.
- `resourceProfile` must be allow-listed.
- `isolationProfile` must be allow-listed.
- Do not accept `runtimeClassName`.
- Do not accept API keys.
- Do not echo sensitive values.

## 4. List sessions

```http
GET /api/v1/sessions
```

Response:

```json
{
  "items": [
    {
      "id": "sess-abc123",
      "phase": "Running",
      "tool": "opencode",
      "modelRef": "default",
      "resourceProfile": "small",
      "isolationProfile": "default",
      "createdAt": "2026-05-12T00:00:00Z",
      "expiresAt": "2026-05-12T02:00:00Z"
    }
  ]
}
```

Only sessions owned by the authenticated user should be returned.

## 5. Get session

```http
GET /api/v1/sessions/{id}
```

Response:

```json
{
  "id": "sess-abc123",
  "phase": "Running",
  "reason": "",
  "message": "",
  "tool": "opencode",
  "modelRef": "default",
  "resourceProfile": "small",
  "isolationProfile": "default",
  "terminalReady": true,
  "createdAt": "2026-05-12T00:00:00Z",
  "expiresAt": "2026-05-12T02:00:00Z"
}
```

Do not return `podName` to normal users unless explicitly needed for debugging and hidden behind admin/debug mode.

## 6. Delete session

```http
DELETE /api/v1/sessions/{id}
```

Response:

```json
{
  "id": "sess-abc123",
  "deleted": true
}
```

The API deletes the AgentSession. The controller cleans owned resources.

## 7. Terminal WebSocket

```http
GET /api/v1/sessions/{id}/terminal
Upgrade: websocket
```

Control messages are JSON text frames:

```json
{
  "type": "resize",
  "cols": 120,
  "rows": 40
}
```

Terminal data frames should be binary frames containing raw terminal bytes.

The server must:

- verify authentication
- verify session ownership
- verify session phase is terminal-connectable
- resolve session -> pod internally
- not accept namespace/pod/container from query parameters
- enforce idle timeout
- close connection when session is deleted/expired

## 8. Health endpoints

```http
GET /healthz
GET /readyz
```

`readyz` should verify that Kubernetes API access is available.

## 9. Model proxy endpoint

Internal to cluster, not exposed publicly:

```http
POST /internal/model-proxy/v1/chat/completions
```

or provider-compatible paths as needed.

Rules:

- Accept only requests from Agent Pods or valid session proxy tokens.
- Translate session proxy token to upstream credential internally.
- Never log request headers containing token values.
- Never log upstream API keys.
- Enforce modelRef/session mapping.

# CLI Spec: caskctl

This document covers the current CLI contract/design, not a permanent CLI-only or CLI-first product scope. Additional clients and agent runtimes are permitted under [Production Requirements](PRODUCTION_REQUIREMENTS.md). Contract changes require compatibility and release evidence.

## 1. Binary name

```text
caskctl
```

## 2. Configuration

Current config file:

```text
~/.caskctl/config.yaml
```

Example:

```yaml
apiServer: https://agentcask.example.com
token: dev-token
```

`dev-token` is a local development example only, not a production credential or identity scheme. Production authentication must meet [Release Criteria](RELEASE_CRITERIA.md).

Environment overrides:

```text
CASK_API_SERVER
CASK_TOKEN
```

## 3. Commands

### session create

```bash
caskctl session create \
  --tool opencode \
  --repo https://gitlab.example.com/team/project.git \
  --branch main \
  --model default \
  --resource small \
  --isolation default \
  --ttl 2h
```

`--tool` currently defaults to `opencode`; this does not fix future runtime priorities. Use `--tool stub` only for deterministic tests, not real agent/provider acceptance.

Output:

```text
ID: sess-abc123
Phase: Pending
```

Machine-readable mode:

```bash
caskctl session create ... -o json
```

### session list

```bash
caskctl session list
```

Output:

```text
ID            TOOL       PHASE      ISOLATION   AGE
sess-abc123   opencode   Running    default     1m
```

### session get

```bash
caskctl session get sess-abc123
```

### session connect

```bash
caskctl session connect sess-abc123
```

Behavior:

- opens WebSocket to `cask-api`
- switches local terminal to raw mode
- forwards stdin to WebSocket
- forwards WebSocket binary frames to stdout
- sends resize messages on terminal resize
- restores terminal state on exit

### session delete

```bash
caskctl session delete sess-abc123
```

## 4. Error handling

The CLI must provide clean messages for:

```text
not authenticated
session not found
session not ready
forbidden
connection dropped
terminal resize unsupported
```

## 5. Security rules

`caskctl` must not:

- accept provider API keys as session creation options
- print proxy tokens by default
- print Kubernetes Pod names by default
- store real model/API keys
- call Kubernetes API directly

## 6. Test requirements

- command parsing tests
- config loading tests
- API client tests with fake server
- WebSocket terminal tests with fake gateway
- terminal raw mode cleanup tests where practical

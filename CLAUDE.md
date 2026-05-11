# CLAUDE.md

## Working mode

Before implementing:

1. Read `AGENTS.md`.
2. Read `PRD.md`.
3. Read `docs/IMPLEMENTATION_PLAN.md`.
4. Produce a short implementation plan.
5. Implement in small, testable steps.

After changing code:

- Run relevant tests.
- Add or update tests for changed behavior.
- Update CRD manifests if API types change.
- Update docs if behavior changes.
- Do not silently alter architecture decisions.

## Non-negotiable MVP constraints

- No Web UI.
- CLI is `caskctl`.
- API server is `cask-api`.
- Controller is `cask-controller`.
- `cask-api` includes terminal gateway for MVP.
- Terminal access is WebSocket -> Kubernetes pods/exec.
- Agent Pods are not externally exposed.
- Users never receive kubeconfig.
- Users never submit raw `runtimeClassName`.
- `isolationProfiles` maps user-facing profiles to Kubernetes runtime settings.
- Real model/API keys never enter Agent Pods.
- Only `cask-api` holds upstream model credentials.

## Definition of done

The task is not done unless:

- code builds
- tests pass
- kind test path is documented and automated
- caskctl can create/list/get/connect/delete sessions
- secret leakage tests pass
- docs are consistent with implemented behavior

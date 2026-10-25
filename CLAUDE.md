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

## Product evolution and security boundaries

- Web UI, management portals and other clients are permitted by product requirements; CLI-only is not a permanent product scope.
- CLI is `caskctl`.
- API server is `cask-api`.
- Internal model proxy is `cask-model-proxy`.
- Controller is `cask-controller`.
- `cask-api` currently includes the terminal gateway; extraction is allowed with an ADR and compatible authentication/API behavior.
- `cask-model-proxy` is internal-only and holds upstream model credentials.
- Current terminal access is WebSocket -> Kubernetes pods/exec. Protocol/backend changes require compatibility, authorization and recovery analysis, not adherence to the initial topology.
- Agent Pods are not externally exposed.
- Users never receive kubeconfig.
- Users never submit raw `runtimeClassName`.
- `isolationProfiles` maps user-facing profiles to Kubernetes runtime settings.
- Real model/API keys never enter Agent Pods.
- Only `cask-model-proxy` holds upstream model credentials.
- Preserve user/session authentication and authorization, least-privilege RBAC, private-by-default networking, resource/data isolation and constrained execution of untrusted code.
- Go services and AgentSession CRDs remain core assets; architecture can evolve through `docs/DESIGN_DECISIONS.md`.
- Provider gateways, persistence, OIDC, security integrations, multi-runtime support, advanced sessions/workspaces, organizations, quotas, billing, HA and horizontal scaling are allowed when justified. They are not all required in this documentation change.

## Production Quality Gate

Use `docs/RELEASE_CRITERIA.md` as the authoritative gate for new features and releases. Existing regression requirements remain necessary:

- code builds
- tests pass
- kind test path is documented and automated
- caskctl can create/list/get/connect/delete sessions
- secret leakage tests pass
- docs are consistent with implemented behavior

Also require real user scenarios, threat modeling and authorization, failure/recovery behavior, multi-user/session validation, stable API/CRD contracts, observability, scalability/maintainability, reproducible configuration/deployment, operational guidance and defined performance/resource budgets. Mock/Fake/Stub success and kind plumbing are not proof of production completeness. State current implementation separately from targets; do not declare missing capabilities ready or trade operational safety for speed.

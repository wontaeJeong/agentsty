# Operations

## Environments

- `local`, developer workflow, process isolation, permissive networking, SQLite, and in-memory doubles where needed
- `dev`, shared integration environment, Kubernetes shaped config, JWT auth, deny by default sandbox egress, durable non-local persistence, and persisted artifact storage
- `staging`, pre production verification, same posture as dev with larger quotas
- `production`, strongest quota and replica settings in the manifest set

## Startup

The API container starts FastAPI through Uvicorn using `agentsty_api.app:create_app`.

Health probes live at `/health` and readiness probes live at `/ready`.

The OpenCode runtime path starts headless from the installed CLI. It launches `opencode serve`, attaches to the local session, runs `opencode run`, and exports the resulting session.

## Configuration

Configuration flows through `AGENTSTY_*` environment variables. The same names are used in the manifests and the shared settings loader.

Important groups include:

- API bind host and port
- gateway base URL, TLS requirement, and audience
- executor backend and isolation mode
- runtime workspace root and network egress controls
- persistence URL and artifact root
- timeout values
- auth mode, required flag, issuer, and audience

Non-local persistence is initialized lazily. The built-in SQLite backend creates its database and runs package-local migrations on first write, while unsupported PostgreSQL URLs fail fast instead of silently falling back to SQLite.

## Day to day tasks

- Roll out one environment at a time.
- Check `/health` first, then `/ready`.
- Confirm the namespace, quota, limit range, RBAC, default-deny network policy, and service account before turning on traffic.
- Watch job cleanup and artifact retention after a failed or cancelled run.
- For non-local runs, confirm the workspace root is writable for sandbox handoff state and that the configured artifact root is writable for durable artifact bytes.

## Scaling notes

- The current non-local API posture stays at one replica because SQLite remains the control-plane persistence backend.
- Sandbox concurrency is profile aware in settings and manifests.
- Tenant quotas rise by environment, and new tenant namespaces are provisioned with quotas, limit ranges, tenant RBAC, and default-deny network policy together.
- Non-local persistence stays tenant scoped, so a single SQLite store can still separate jobs and idempotency by tenant while artifact content references remain job-scoped.

## Incident notes

- Authentication failures usually mean issuer, audience, or token provider wiring is wrong.
- Gateway failures should map back to the shared error taxonomy.
- Sandbox failures should be checked against runtimeClass, quota, and network policy first.
- Persistence failures should be checked against workspace permissions, artifact-root permissions, SQLite file locks, migration state, and storage mounts before assuming a repository bug.
- Kubernetes control-plane failures should first be checked against in-cluster service-account token mounting or an explicitly configured kubeconfig/context.

## Runbook caution

The local profile is not a shortcut to production. It is a separate execution path, useful for smoke checks and fast iteration, but it does not provide the same isolation guarantees as the Kubernetes shaped environments.

Non-local is the implemented production code path in the repo. Cluster admission, credentials, and storage-class behavior still need environment-specific operator validation during rollout.

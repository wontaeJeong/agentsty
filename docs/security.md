# Security

## Security posture

The platform is built around internal gateway access, tenant scoped identifiers, authenticated non-local requests, and sandboxed execution. The code and manifests both enforce a clean split between local development and non-local environments.

## Secrets and credentials

- Do not place real secrets in ConfigMaps.
- Use Kubernetes Secrets or an external secret manager for JWT material, database credentials, gateway credentials, and any vendor tokens.
- The runtime settings keep vendor credentials disabled for sandbox work.
- Local mode allows anonymous access only when the profile says so.
- Non-local profiles require bearer auth or a verified principal supplied by upstream auth.

## Authentication and gateway access

- Non-local profiles require authentication.
- Gateway access must be internal only.
- TLS is required outside local development.
- The shared gateway client rejects missing token providers in authenticated profiles.
- Requests are tenant bound after auth, so the tenant in the request must match the tenant claims on the principal.

## Network policy

- Control plane namespaces are separate from tenant sandbox namespaces.
- Non-local control-plane pods authenticate to Kubernetes with their mounted service-account token by default, while tenant sandbox service accounts keep token automount disabled.
- Non-local manifests use deny by default egress for tenant sandboxes.
- Allowlisted egress is limited to gateway, identity, data, and DNS paths described in the manifests.
- Local manifests stay permissive enough for developer workflows, but that is not a production posture.

## Sandbox isolation

- Local mode uses process isolation only.
- Dev, staging, and prod are modeled as Kubernetes sandboxes with virtual machine isolation in the settings contract.
- Privileged containers stay disabled.
- RuntimeClass settings point to Kata shaped isolation in the non-local manifests.

## Tenant isolation

- Tenant IDs are part of request and job identifiers.
- Tenants get separate namespaces, quotas, limit ranges, service accounts, role bindings, and default-deny sandbox policies in the manifests and runtime provisioning path.
- Sandbox job names and storage paths are tenant scoped.

## Persistence and artifacts

- Local mode uses SQLite in the workspace by default.
- Non-local persistence is SQLite-backed, with lazy migration startup and tenant-scoped tables for jobs, idempotency, audit events, and artifact metadata.
- The manifests pin supported `sqlite:///` URLs, and the non-local service-state root is mounted from the same shared NFS-backed storage in both the API pod and sandbox jobs rather than from pod-local `emptyDir`.
- Artifact bytes stay outside the metadata tables, which keeps the metadata store easier to redact and inspect.

## Logging and artifacts

- Structured logs redact obvious secret keys.
- Artifact persistence is configured to redact sensitive artifacts.
- Keep request bodies, tokens, and credentials out of debug logs.

## Operational boundary

The docs and manifests now describe the implemented non-local security shape. Live cluster rollout still depends on environment-owned storage classes, credentials, and policy outside the repository.

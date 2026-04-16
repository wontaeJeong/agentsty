# Deployment

## Deployment targets

The repository ships manifest bundles for `local`, `dev`, `staging`, and `production` under `deploy/k8s/`.

Each bundle includes the API namespace, quotas, limits, service account, RBAC, config map, deployment, service, network policy, tenant sandbox namespace, and a smoke job. The matching container build recipes live under `deploy/images/`.

## Local

- Uses `AGENTSTY_PROFILE=local`
- Uses process isolation
- Uses HTTP gateway settings and anonymous local access
- Uses SQLite-backed local state in the workspace
- Keeps the sandbox runner path local and lightweight

## Dev, staging, production

- Use `AGENTSTY_EXECUTOR_BACKEND=kubernetes`
- Use `AGENTSTY_EXECUTOR_ISOLATION_MODE=virtual_machine`
- Require HTTPS gateway access
- Require JWT auth
- Apply deny by default tenant egress
- Use Kata shaped `RuntimeClass` settings in the manifest contract
- Use the durable non-local persistence path with a supported `sqlite:///` URL, package-local migrations, and artifact bytes stored under the configured artifact root
- Use the API pod's in-cluster service-account token for Kubernetes control-plane authentication by default; use kubeconfig only for out-of-cluster operator workflows
- Back the non-local service-state and artifact roots with shared NFS-backed storage that is mounted into both the API pod and sandbox jobs rather than pod-local ephemeral storage
- Keep the non-local API Deployment at one replica while SQLite remains the shared control-plane database

## Release flow

1. Build the API and sandbox images with `IMAGE_TAG=<env-tag> ./deploy/images/build-images.sh`.
2. Push `ghcr.io/agentsty/agentsty-api:<env-tag>` and `ghcr.io/agentsty/agentsty-sandbox:<env-tag>` to the target registry.
3. Apply the target environment manifest set.
4. Check probes, logs, and tenant namespace resources.
5. Run a smoke request through `/v1/chat/completions`.

For non-local releases, make sure the shared NFS export configured for the environment is mounted read-write in both the API pod and sandbox jobs so the repository can create its database, migration markers, runtime handoff state, and persisted artifact content. The sandbox image build also needs outbound access to install the `opencode-ai` npm package during `docker build`.

## Rollback

Rollback should restore the previous manifest set and image tag first. If a failure is isolated to tenant sandboxes, clear the affected jobs and inspect quota, network policy, and runtimeClass settings before retrying.

## Operational note

The repo now ships the implemented non-local control-plane, persistence, and artifact-storage code paths that the manifests target. Live cluster rollout still depends on environment credentials, storage classes, and operator-owned cluster policy outside the repository.

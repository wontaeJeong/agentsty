# Container image builds

This directory contains the in-repo build definitions for the non-local images referenced by `deploy/k8s/*/agentsty.yaml`.

## Images

- `api.Dockerfile` builds `ghcr.io/agentsty/agentsty-api:<tag>`
- `sandbox.Dockerfile` builds `ghcr.io/agentsty/agentsty-sandbox:<tag>`

Both Dockerfiles build the uv workspace packages inside the image build, then install the resulting wheels into an isolated virtualenv. The sandbox image also installs the `opencode` CLI via the published `opencode-ai` npm package so the packaged runner can execute the real headless runtime path.

## Build

From the repository root:

```bash
IMAGE_TAG=dev ./deploy/images/build-images.sh
```

Optional overrides:

- `REGISTRY` defaults to `ghcr.io/agentsty`
- `IMAGE_TAG` defaults to `dev`
- `PYTHON_IMAGE` defaults to `python:3.13-slim`
- `OPENCODE_NPM_PACKAGE` defaults to `opencode-ai@latest`

Examples:

```bash
REGISTRY=ghcr.io/agentsty IMAGE_TAG=staging ./deploy/images/build-images.sh
REGISTRY=ghcr.io/agentsty IMAGE_TAG=prod ./deploy/images/build-images.sh
```

The resulting image tags match the non-local manifests:

- dev: `ghcr.io/agentsty/agentsty-api:dev`, `ghcr.io/agentsty/agentsty-sandbox:dev`
- staging: `ghcr.io/agentsty/agentsty-api:staging`, `ghcr.io/agentsty/agentsty-sandbox:staging`
- production/prod: `ghcr.io/agentsty/agentsty-api:prod`, `ghcr.io/agentsty/agentsty-sandbox:prod`

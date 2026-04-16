# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.13-slim
ARG OPENCODE_NPM_PACKAGE=opencode-ai@latest

FROM ${PYTHON_IMAGE} AS builder
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/root/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv "$VIRTUAL_ENV" && pip install --no-cache-dir "uv>=0.8,<1"
RUN npm install -g "$OPENCODE_NPM_PACKAGE"

WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/api/pyproject.toml packages/api/pyproject.toml
COPY packages/platform/pyproject.toml packages/platform/pyproject.toml
COPY packages/runtime-opencode/pyproject.toml packages/runtime-opencode/pyproject.toml
COPY packages/executor-kubernetes/pyproject.toml packages/executor-kubernetes/pyproject.toml
COPY packages ./packages
RUN uv build --all-packages --out-dir /tmp/dist --no-create-gitignore \
    && pip install --no-cache-dir \
        /tmp/dist/agentsty_platform-*.whl \
        /tmp/dist/agentsty_runtime_opencode-*.whl \
        /tmp/dist/agentsty_executor_kubernetes-*.whl

FROM ${PYTHON_IMAGE} AS runtime
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:$PATH \
    HOME=/home/agentsty

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv "$VIRTUAL_ENV"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/opencode /usr/local/bin/opencode
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/opencode-ai/bin.js /usr/local/bin/opencode-ai \
    && useradd --create-home --shell /usr/sbin/nologin agentsty \
    && mkdir -p /workspace \
    && chown -R agentsty:agentsty /workspace /home/agentsty
USER agentsty
WORKDIR /workspace
CMD ["python", "-m", "agentsty_platform.runner", "serve"]

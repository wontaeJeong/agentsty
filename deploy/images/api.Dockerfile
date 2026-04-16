# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS builder
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/root/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv "$VIRTUAL_ENV" && pip install --no-cache-dir "uv>=0.8,<1"

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
        /tmp/dist/agentsty_executor_kubernetes-*.whl \
        /tmp/dist/agentsty_api-*.whl

FROM ${PYTHON_IMAGE} AS runtime
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv "$VIRTUAL_ENV"
COPY --from=builder /opt/venv /opt/venv
RUN useradd --create-home --shell /usr/sbin/nologin agentsty
USER agentsty
WORKDIR /app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "agentsty_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)
REGISTRY=${REGISTRY:-ghcr.io/agentsty}
IMAGE_TAG=${IMAGE_TAG:-dev}
PYTHON_IMAGE=${PYTHON_IMAGE:-python:3.13-slim}
OPENCODE_NPM_PACKAGE=${OPENCODE_NPM_PACKAGE:-opencode-ai@latest}

build_image() {
  local dockerfile=$1
  local image_name=$2

  docker build \
    --file "$REPO_ROOT/deploy/images/${dockerfile}" \
    --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" \
    --build-arg "OPENCODE_NPM_PACKAGE=$OPENCODE_NPM_PACKAGE" \
    --tag "$REGISTRY/$image_name:$IMAGE_TAG" \
    "$REPO_ROOT"
}

build_image api.Dockerfile agentsty-api
build_image sandbox.Dockerfile agentsty-sandbox

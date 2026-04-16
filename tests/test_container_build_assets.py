from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_IMAGES = ROOT / "deploy" / "images"
NON_LOCAL_MANIFESTS = (
    ROOT / "deploy" / "k8s" / "dev" / "agentsty.yaml",
    ROOT / "deploy" / "k8s" / "staging" / "agentsty.yaml",
    ROOT / "deploy" / "k8s" / "prod" / "agentsty.yaml",
)


def test_in_repo_container_build_definitions_exist_for_non_local_images() -> None:
    assert (DEPLOY_IMAGES / "api.Dockerfile").is_file()
    assert (DEPLOY_IMAGES / "sandbox.Dockerfile").is_file()
    assert (DEPLOY_IMAGES / "build-images.sh").is_file()
    assert (DEPLOY_IMAGES / "README.md").is_file()
    assert (ROOT / ".dockerignore").is_file()


def test_build_script_targets_manifest_image_names() -> None:
    script = (DEPLOY_IMAGES / "build-images.sh").read_text(encoding="utf-8")

    assert "agentsty-api" in script
    assert "agentsty-sandbox" in script
    assert "ghcr.io/agentsty" in script
    assert "IMAGE_TAG" in script


def test_dockerfiles_install_workspace_packages_and_runtime_entrypoints() -> None:
    api = (DEPLOY_IMAGES / "api.Dockerfile").read_text(encoding="utf-8")
    sandbox = (DEPLOY_IMAGES / "sandbox.Dockerfile").read_text(encoding="utf-8")

    assert "uv build --all-packages" in api
    assert "agentsty_api-*.whl" in api
    assert "uvicorn" in api

    assert "uv build --all-packages" in sandbox
    assert "agentsty_runtime_opencode-*.whl" in sandbox
    assert 'npm install -g "$OPENCODE_NPM_PACKAGE"' in sandbox
    assert "agentsty_platform.runner" in sandbox
    assert "opencode" in sandbox


def test_non_local_manifests_match_documented_image_tags() -> None:
    readme = (DEPLOY_IMAGES / "README.md").read_text(encoding="utf-8")

    assert "agentsty-api:dev" in readme
    assert "agentsty-sandbox:dev" in readme
    assert "agentsty-api:staging" in readme
    assert "agentsty-sandbox:staging" in readme
    assert "agentsty-api:prod" in readme
    assert "agentsty-sandbox:prod" in readme

    for manifest in NON_LOCAL_MANIFESTS:
        text = manifest.read_text(encoding="utf-8")
        assert "ghcr.io/agentsty/agentsty-api:" in text
        assert "ghcr.io/agentsty/agentsty-sandbox:" in text

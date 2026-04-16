from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = ROOT / "deploy" / "k8s"
ENVIRONMENTS = ("local", "dev", "staging", "prod")
REQUIRED_KINDS = {
    "Namespace",
    "ResourceQuota",
    "LimitRange",
    "ServiceAccount",
    "ClusterRole",
    "ClusterRoleBinding",
    "ConfigMap",
    "Deployment",
    "Service",
    "NetworkPolicy",
    "Role",
    "RoleBinding",
    "Job",
}
CONFIG_KEYS = {
    "AGENTSTY_PROFILE",
    "AGENTSTY_GATEWAY_BASE_URL",
    "AGENTSTY_GATEWAY_REQUIRE_TLS",
    "AGENTSTY_EXECUTOR_BACKEND",
    "AGENTSTY_EXECUTOR_ISOLATION_MODE",
    "AGENTSTY_RUNTIME_BACKEND",
    "AGENTSTY_RUNTIME_WORKSPACE_ROOT",
    "AGENTSTY_RUNTIME_ALLOW_NETWORK_EGRESS",
    "AGENTSTY_RUNTIME_EXPOSE_VENDOR_CREDENTIALS",
    "AGENTSTY_PERSISTENCE_DATABASE_URL",
    "AGENTSTY_PERSISTENCE_ARTIFACT_ROOT",
    "AGENTSTY_TIMEOUT_REQUEST_SECONDS",
    "AGENTSTY_TIMEOUT_EXECUTION_SECONDS",
    "AGENTSTY_KUBERNETES_SHARED_STATE_SERVER",
    "AGENTSTY_KUBERNETES_SHARED_STATE_PATH",
    "AGENTSTY_AUTH_MODE",
    "AGENTSTY_AUTH_REQUIRED",
    "AGENTSTY_AUTH_ALLOW_ANONYMOUS_LOCAL",
}


def _load_environment(env: str) -> list[dict[str, Any]]:
    manifest_path = DEPLOY_ROOT / env / "agentsty.yaml"
    with manifest_path.open("r", encoding="utf-8") as handle:
        documents = [doc for doc in yaml.safe_load_all(handle) if doc is not None]
    return documents


def _by_kind(documents: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [document for document in documents if document["kind"] == kind]


def _one(documents: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    for document in documents:
        metadata = document.get("metadata", {})
        if document["kind"] == kind and metadata.get("name") == name:
            return document
    raise AssertionError(f"missing {kind}/{name}")


def test_all_environment_manifests_exist_and_parse() -> None:
    for env in ENVIRONMENTS:
        documents = _load_environment(env)
        kinds = {document["kind"] for document in documents}
        assert REQUIRED_KINDS.issubset(kinds)


def test_environment_manifests_match_platform_settings_contract() -> None:
    expected_profiles = {
        "local": "local",
        "dev": "dev",
        "staging": "staging",
        "prod": "production",
    }
    expected_database_urls = {
        "local": "sqlite:////var/lib/agentsty/local/agentsty.db",
        "dev": "sqlite:////var/lib/agentsty/dev/runtime/_service_state/nonlocal-persistence.sqlite3",
        "staging": "sqlite:////var/lib/agentsty/staging/runtime/_service_state/nonlocal-persistence.sqlite3",
        "prod": "sqlite:////var/lib/agentsty/production/runtime/_service_state/nonlocal-persistence.sqlite3",
    }
    expected_shared_state_servers = {
        "dev": "agentsty-state.dev.internal",
        "staging": "agentsty-state.staging.internal",
        "prod": "agentsty-state.production.internal",
    }
    expected_shared_state_paths = {
        "dev": "/exports/agentsty/dev",
        "staging": "/exports/agentsty/staging",
        "prod": "/exports/agentsty/production",
    }

    for env in ENVIRONMENTS:
        documents = _load_environment(env)
        config_map = _one(documents, "ConfigMap", "agentsty-platform-settings")
        data = config_map["data"]
        required_keys = (
            CONFIG_KEYS
            if env != "local"
            else (
                CONFIG_KEYS
                - {
                    "AGENTSTY_KUBERNETES_SHARED_STATE_SERVER",
                    "AGENTSTY_KUBERNETES_SHARED_STATE_PATH",
                }
            )
        )
        assert required_keys.issubset(data.keys())
        assert data["AGENTSTY_PROFILE"] == expected_profiles[env]
        assert data["AGENTSTY_PERSISTENCE_DATABASE_URL"] == expected_database_urls[env]

        if env == "local":
            assert data["AGENTSTY_EXECUTOR_BACKEND"] == "local"
            assert data["AGENTSTY_EXECUTOR_ISOLATION_MODE"] == "process"
            assert data["AGENTSTY_GATEWAY_BASE_URL"].startswith("http://")
            assert data["AGENTSTY_GATEWAY_REQUIRE_TLS"] == "false"
            assert data["AGENTSTY_AUTH_REQUIRED"] == "false"
            assert data["AGENTSTY_AUTH_ALLOW_ANONYMOUS_LOCAL"] == "true"
        else:
            assert data["AGENTSTY_EXECUTOR_BACKEND"] == "kubernetes"
            assert data["AGENTSTY_EXECUTOR_ISOLATION_MODE"] == "virtual_machine"
            assert data["AGENTSTY_GATEWAY_BASE_URL"].startswith("https://")
            assert data["AGENTSTY_GATEWAY_REQUIRE_TLS"] == "true"
            assert data["AGENTSTY_AUTH_REQUIRED"] == "true"
            assert data["AGENTSTY_AUTH_ALLOW_ANONYMOUS_LOCAL"] == "false"
            assert (
                data["AGENTSTY_KUBERNETES_SHARED_STATE_SERVER"]
                == expected_shared_state_servers[env]
            )
            assert (
                data["AGENTSTY_KUBERNETES_SHARED_STATE_PATH"]
                == expected_shared_state_paths[env]
            )


def test_deployments_and_jobs_encode_expected_security_posture() -> None:
    local_documents = _load_environment("local")
    prod_documents = _load_environment("prod")

    local_deployment = _one(local_documents, "Deployment", "agentsty-api")
    prod_deployment = _one(prod_documents, "Deployment", "agentsty-api")

    assert local_deployment["spec"]["replicas"] == 1
    assert prod_deployment["spec"]["replicas"] == 1

    dev_documents = _load_environment("dev")
    dev_deployment = _one(dev_documents, "Deployment", "agentsty-api")
    dev_service_account = _one(dev_documents, "ServiceAccount", "agentsty-api")
    prod_service_account = _one(prod_documents, "ServiceAccount", "agentsty-api")

    local_container = local_deployment["spec"]["template"]["spec"]["containers"][0]
    prod_container = prod_deployment["spec"]["template"]["spec"]["containers"][0]
    assert local_container["resources"]["requests"]["cpu"] == "100m"
    assert prod_container["resources"]["requests"]["cpu"] == "1"
    assert local_container["securityContext"]["allowPrivilegeEscalation"] is False
    assert prod_container["securityContext"]["allowPrivilegeEscalation"] is False
    assert (
        dev_deployment["spec"]["template"]["spec"]["automountServiceAccountToken"]
        is True
    )
    assert (
        prod_deployment["spec"]["template"]["spec"]["automountServiceAccountToken"]
        is True
    )
    assert dev_service_account["automountServiceAccountToken"] is True
    assert prod_service_account["automountServiceAccountToken"] is True

    local_job = _one(local_documents, "Job", "sandbox-smoke-local")
    prod_job = _one(prod_documents, "Job", "sandbox-smoke-prod")
    local_job_spec = local_job["spec"]["template"]["spec"]
    prod_job_spec = prod_job["spec"]["template"]["spec"]

    assert "runtimeClassName" not in local_job_spec
    assert prod_job_spec["runtimeClassName"] == "kata-clh"
    assert prod_job_spec["automountServiceAccountToken"] is False
    assert prod_job_spec["containers"][0]["securityContext"]["runAsNonRoot"] is True


def test_non_local_manifests_mount_shared_nfs_state_for_api_and_sandbox() -> None:
    expected_servers = {
        "dev": "agentsty-state.dev.internal",
        "staging": "agentsty-state.staging.internal",
        "prod": "agentsty-state.production.internal",
    }
    expected_paths = {
        "dev": "/exports/agentsty/dev",
        "staging": "/exports/agentsty/staging",
        "prod": "/exports/agentsty/production",
    }
    expected_mount_paths = {
        "dev": "/var/lib/agentsty/dev",
        "staging": "/var/lib/agentsty/staging",
        "prod": "/var/lib/agentsty/production",
    }

    for env in expected_servers:
        documents = _load_environment(env)
        deployment = _one(documents, "Deployment", "agentsty-api")
        deployment_spec = deployment["spec"]["template"]["spec"]
        assert deployment_spec["volumes"] == [
            {
                "name": "agentsty-state",
                "nfs": {
                    "server": expected_servers[env],
                    "path": expected_paths[env],
                    "readOnly": False,
                },
            }
        ]

        container = deployment_spec["containers"][0]
        assert container["volumeMounts"] == [
            {
                "name": "agentsty-state",
                "mountPath": expected_mount_paths[env],
            }
        ]

        smoke_job = _one(documents, "Job", f"sandbox-smoke-{env}")
        smoke_spec = smoke_job["spec"]["template"]["spec"]
        smoke_container = smoke_spec["containers"][0]
        assert smoke_container["volumeMounts"] == [
            {
                "name": "agentsty-state",
                "mountPath": expected_mount_paths[env],
            }
        ]
        assert smoke_spec["volumes"] == deployment_spec["volumes"]


def test_network_policies_and_tenant_boundaries_are_present_for_every_environment() -> (
    None
):
    for env in ENVIRONMENTS:
        documents = _load_environment(env)
        network_policies = _by_kind(documents, "NetworkPolicy")
        namespaces = _by_kind(documents, "Namespace")
        service_accounts = _by_kind(documents, "ServiceAccount")
        roles = _by_kind(documents, "Role")
        role_bindings = _by_kind(documents, "RoleBinding")
        quotas = _by_kind(documents, "ResourceQuota")
        limits = _by_kind(documents, "LimitRange")

        assert len(network_policies) >= 2
        assert len(namespaces) == 2
        assert len(service_accounts) == 2
        assert len(roles) == 1
        assert len(role_bindings) == 1
        assert len(quotas) == 2
        assert len(limits) == 2

        if env != "local":
            runtime_class = _one(documents, "RuntimeClass", "kata-clh")
            assert runtime_class["handler"] == "kata-clh"
            tenant_policy = _one(
                documents, "NetworkPolicy", "tenant-sandbox-default-deny"
            )
            assert tenant_policy["spec"]["ingress"] == []
            assert len(tenant_policy["spec"]["egress"]) == 4

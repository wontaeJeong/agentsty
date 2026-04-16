"""Real Kubernetes API-backed helpers for non-local control-plane operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from .models import (
    KubernetesJobIsolationSettings,
    KubernetesJobManifest,
    KubernetesJobObservation,
    KubernetesJobPhase,
    KubernetesJobResources,
    KubernetesTenantBoundary,
    SandboxResourceIdentityLike,
)

_CANCELLATION_REQUESTED_AT = "agentsty.io/cancellation-requested-at"
_CANCELLATION_REASON = "agentsty.io/cancellation-reason"


class _CoreV1ApiLike(Protocol):
    def read_namespace(self, name: str) -> object: ...

    def create_namespace(self, body: object) -> object: ...

    def read_namespaced_service_account(self, name: str, namespace: str) -> object: ...

    def create_namespaced_service_account(
        self, namespace: str, body: object
    ) -> object: ...

    def read_namespaced_resource_quota(self, name: str, namespace: str) -> object: ...

    def create_namespaced_resource_quota(
        self, namespace: str, body: object
    ) -> object: ...

    def read_namespaced_limit_range(self, name: str, namespace: str) -> object: ...

    def create_namespaced_limit_range(self, namespace: str, body: object) -> object: ...

    def delete_collection_namespaced_pod(
        self,
        namespace: str,
        *,
        label_selector: str,
        body: object,
    ) -> object: ...


class _BatchV1ApiLike(Protocol):
    def create_namespaced_job(self, namespace: str, body: object) -> object: ...

    def read_namespaced_job(self, name: str, namespace: str) -> object: ...

    def patch_namespaced_job(
        self, name: str, namespace: str, body: object
    ) -> object: ...

    def delete_namespaced_job(
        self, name: str, namespace: str, body: object
    ) -> object: ...


class _RbacAuthorizationV1ApiLike(Protocol):
    def read_namespaced_role(self, name: str, namespace: str) -> object: ...

    def create_namespaced_role(self, namespace: str, body: object) -> object: ...

    def read_namespaced_role_binding(self, name: str, namespace: str) -> object: ...

    def create_namespaced_role_binding(
        self, namespace: str, body: object
    ) -> object: ...


class _NetworkingV1ApiLike(Protocol):
    def read_namespaced_network_policy(self, name: str, namespace: str) -> object: ...

    def create_namespaced_network_policy(
        self, namespace: str, body: object
    ) -> object: ...


class _KubernetesSettingsLike(Protocol):
    api_server_url: str
    kubeconfig_path: Path | None
    kube_context: str | None


class _ProfileValue(Protocol):
    value: str


class _SettingsLike(Protocol):
    profile: _ProfileValue | str
    kubernetes: _KubernetesSettingsLike


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_metadata(metadata: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return {key: value for key, value in metadata}


def _get_value(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list_items(value: object | None) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string(value: object | None, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _int(value: object | None, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if value is None:
        return default
    return int(str(value))


def _bool(value: object | None, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _datetime_from_value(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _cpu_quantity(millis: int) -> str:
    return f"{millis}m"


def _memory_quantity(mebibytes: int) -> str:
    return f"{mebibytes}Mi"


def _parse_cpu_millis(value: object | None, default: int) -> int:
    text = _string(value).strip()
    if not text:
        return default
    if text.endswith("m"):
        return int(text[:-1])
    return int(float(text) * 1000)


def _parse_mebibytes(value: object | None, default: int) -> int:
    text = _string(value).strip()
    if not text:
        return default
    if text.endswith("Mi"):
        return int(text[:-2])
    if text.endswith("Gi"):
        return int(float(text[:-2]) * 1024)
    return int(text)


def _api_error_status(error: BaseException) -> int | None:
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status
    if status is None:
        return None
    return int(str(status))


def _profile_name(profile: _ProfileValue | str) -> str:
    return profile if isinstance(profile, str) else profile.value


@dataclass(slots=True)
class KubernetesApiClient:
    """Lazy wrapper around the official Kubernetes Python client."""

    server_url: str
    profile: str = "production"
    kubeconfig_path: Path | None = None
    kube_context: str | None = None
    _core_api: _CoreV1ApiLike | None = field(default=None, init=False, repr=False)
    _batch_api: _BatchV1ApiLike | None = field(default=None, init=False, repr=False)
    _rbac_api: _RbacAuthorizationV1ApiLike | None = field(
        default=None, init=False, repr=False
    )
    _networking_api: _NetworkingV1ApiLike | None = field(
        default=None, init=False, repr=False
    )

    @classmethod
    def from_settings(cls, settings: _SettingsLike) -> KubernetesApiClient:
        return cls(
            server_url=settings.kubernetes.api_server_url,
            profile=_profile_name(settings.profile),
            kubeconfig_path=settings.kubernetes.kubeconfig_path,
            kube_context=settings.kubernetes.kube_context,
        )

    def ensure_namespace(self, boundary: KubernetesTenantBoundary) -> None:
        core_api = self._core_api_client()
        rbac_api = self._rbac_api_client()
        networking_api = self._networking_api_client()
        namespace_body = {
            "metadata": {
                "name": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            }
        }
        try:
            core_api.read_namespace(boundary.namespace)
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            core_api.create_namespace(namespace_body)

        service_account_body = {
            "metadata": {
                "name": boundary.service_account_name,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            },
            "automountServiceAccountToken": False,
        }
        try:
            core_api.read_namespaced_service_account(
                boundary.service_account_name,
                boundary.namespace,
            )
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            core_api.create_namespaced_service_account(
                boundary.namespace,
                service_account_body,
            )

        quota_name = "tenant-sandbox-quota"
        try:
            core_api.read_namespaced_resource_quota(quota_name, boundary.namespace)
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            core_api.create_namespaced_resource_quota(
                boundary.namespace,
                self._resource_quota_body(boundary, quota_name),
            )

        limit_range_name = "tenant-sandbox-limits"
        try:
            core_api.read_namespaced_limit_range(limit_range_name, boundary.namespace)
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            core_api.create_namespaced_limit_range(
                boundary.namespace,
                self._limit_range_body(boundary, limit_range_name),
            )

        role_name = "agentsty-sandbox-runner"
        try:
            rbac_api.read_namespaced_role(role_name, boundary.namespace)
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            rbac_api.create_namespaced_role(
                boundary.namespace,
                self._role_body(boundary, role_name),
            )

        role_binding_name = "agentsty-sandbox-runner"
        try:
            rbac_api.read_namespaced_role_binding(role_binding_name, boundary.namespace)
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            rbac_api.create_namespaced_role_binding(
                boundary.namespace,
                self._role_binding_body(boundary, role_binding_name, role_name),
            )

        network_policy_name = "tenant-sandbox-default-deny"
        try:
            networking_api.read_namespaced_network_policy(
                network_policy_name,
                boundary.namespace,
            )
        except Exception as error:
            if _api_error_status(error) != 404:
                raise
            networking_api.create_namespaced_network_policy(
                boundary.namespace,
                self._default_deny_network_policy_body(boundary, network_policy_name),
            )

    def create_job(self, manifest: KubernetesJobManifest) -> None:
        batch_api = self._batch_api_client()
        try:
            batch_api.create_namespaced_job(
                manifest.tenant_boundary.namespace,
                self._job_body(manifest),
            )
        except Exception as error:
            if _api_error_status(error) == 409:
                raise ValueError("job already exists") from error
            raise

    def read_job(
        self, namespace: str, job_name: str
    ) -> KubernetesJobObservation | None:
        batch_api = self._batch_api_client()
        try:
            job = batch_api.read_namespaced_job(job_name, namespace)
        except Exception as error:
            if _api_error_status(error) == 404:
                return None
            raise
        return self._observation_from_job(job)

    def cancel_job(
        self,
        namespace: str,
        job_name: str,
        *,
        requested_at: datetime,
        reason: str | None = None,
        error: object | None = None,
    ) -> bool:
        batch_api = self._batch_api_client()
        core_api = self._core_api_client()
        annotation_patch = {
            _CANCELLATION_REQUESTED_AT: _isoformat(requested_at),
        }
        if reason is not None:
            annotation_patch[_CANCELLATION_REASON] = reason
        try:
            batch_api.patch_namespaced_job(
                job_name,
                namespace,
                {
                    "metadata": {"annotations": annotation_patch},
                    "spec": {"suspend": True},
                },
            )
        except Exception as patch_error:
            if _api_error_status(patch_error) == 404:
                return False
            raise
        self._delete_job_pods(core_api, namespace, job_name)
        return True

    def delete_job(self, namespace: str, job_name: str) -> bool:
        batch_api = self._batch_api_client()
        core_api = self._core_api_client()
        try:
            batch_api.delete_namespaced_job(
                job_name,
                namespace,
                {"propagationPolicy": "Background"},
            )
        except Exception as error:
            if _api_error_status(error) == 404:
                return False
            raise
        self._delete_job_pods(core_api, namespace, job_name)
        return True

    def _delete_job_pods(
        self,
        core_api: _CoreV1ApiLike,
        namespace: str,
        job_name: str,
    ) -> None:
        try:
            core_api.delete_collection_namespaced_pod(
                namespace,
                label_selector=f"job-name={job_name}",
                body={"gracePeriodSeconds": 0},
            )
        except Exception as error:
            if _api_error_status(error) != 404:
                raise

    def _core_api_client(self) -> _CoreV1ApiLike:
        self._ensure_clients()
        return cast(_CoreV1ApiLike, self._core_api)

    def _batch_api_client(self) -> _BatchV1ApiLike:
        self._ensure_clients()
        return cast(_BatchV1ApiLike, self._batch_api)

    def _rbac_api_client(self) -> _RbacAuthorizationV1ApiLike:
        self._ensure_clients()
        return cast(_RbacAuthorizationV1ApiLike, self._rbac_api)

    def _networking_api_client(self) -> _NetworkingV1ApiLike:
        self._ensure_clients()
        return cast(_NetworkingV1ApiLike, self._networking_api)

    def _tenant_quota_hard_limits(self) -> dict[str, str]:
        profile = "production" if self.profile == "prod" else self.profile
        if profile == "dev":
            return {
                "count/jobs.batch": "4",
                "pods": "4",
                "requests.cpu": "2",
                "requests.memory": "2Gi",
                "limits.cpu": "4",
                "limits.memory": "4Gi",
            }
        if profile == "staging":
            return {
                "count/jobs.batch": "8",
                "pods": "8",
                "requests.cpu": "4",
                "requests.memory": "4Gi",
                "limits.cpu": "8",
                "limits.memory": "8Gi",
            }
        return {
            "count/jobs.batch": "12",
            "pods": "12",
            "requests.cpu": "6",
            "requests.memory": "8Gi",
            "limits.cpu": "12",
            "limits.memory": "16Gi",
        }

    def _tenant_limit_range_defaults(self) -> tuple[dict[str, str], dict[str, str]]:
        profile = "production" if self.profile == "prod" else self.profile
        if profile == "dev":
            return (
                {"cpu": "250m", "memory": "256Mi"},
                {"cpu": "500m", "memory": "512Mi"},
            )
        if profile == "staging":
            return (
                {"cpu": "250m", "memory": "512Mi"},
                {"cpu": "1", "memory": "1Gi"},
            )
        return (
            {"cpu": "500m", "memory": "1Gi"},
            {"cpu": "2", "memory": "2Gi"},
        )

    def _resource_quota_body(
        self, boundary: KubernetesTenantBoundary, name: str
    ) -> dict[str, object]:
        return {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {
                "name": name,
                "namespace": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            },
            "spec": {"hard": self._tenant_quota_hard_limits()},
        }

    def _limit_range_body(
        self, boundary: KubernetesTenantBoundary, name: str
    ) -> dict[str, object]:
        default_request, default_limits = self._tenant_limit_range_defaults()
        return {
            "apiVersion": "v1",
            "kind": "LimitRange",
            "metadata": {
                "name": name,
                "namespace": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            },
            "spec": {
                "limits": [
                    {
                        "type": "Container",
                        "defaultRequest": default_request,
                        "default": default_limits,
                    }
                ]
            },
        }

    def _role_body(
        self, boundary: KubernetesTenantBoundary, name: str
    ) -> dict[str, object]:
        return {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {
                "name": name,
                "namespace": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["pods", "pods/log"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["batch"],
                    "resources": ["jobs"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        }

    def _role_binding_body(
        self,
        boundary: KubernetesTenantBoundary,
        name: str,
        role_name: str,
    ) -> dict[str, object]:
        return {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": name,
                "namespace": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": _normalize_metadata(boundary.annotations),
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": role_name,
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": boundary.service_account_name,
                    "namespace": boundary.namespace,
                }
            ],
        }

    def _default_deny_network_policy_body(
        self, boundary: KubernetesTenantBoundary, name: str
    ) -> dict[str, object]:
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": name,
                "namespace": boundary.namespace,
                "labels": _normalize_metadata(boundary.labels),
                "annotations": {
                    **_normalize_metadata(boundary.annotations),
                    "agentsty.io/posture": "deny-by-default-with-internal-allowlist",
                    "agentsty.io/allowlist-note": (
                        "Target namespaces must be labeled "
                        "agentsty.io/network-role={gateway,identity,data} to receive sandbox egress."
                    ),
                },
            },
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [],
                "egress": [
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "kube-system"
                                    }
                                }
                            }
                        ],
                        "ports": [
                            {"protocol": "UDP", "port": 53},
                            {"protocol": "TCP", "port": 53},
                        ],
                    },
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "agentsty.io/network-role": "gateway"
                                    }
                                }
                            }
                        ],
                        "ports": [{"protocol": "TCP", "port": 443}],
                    },
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "agentsty.io/network-role": "identity"
                                    }
                                }
                            }
                        ],
                        "ports": [{"protocol": "TCP", "port": 443}],
                    },
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {"agentsty.io/network-role": "data"}
                                }
                            }
                        ],
                        "ports": [{"protocol": "TCP", "port": 5432}],
                    },
                ],
            },
        }

    def _ensure_clients(self) -> None:
        if (
            self._core_api is not None
            and self._batch_api is not None
            and self._rbac_api is not None
            and self._networking_api is not None
        ):
            return
        client_module = cast(Any, import_module("kubernetes.client"))
        config_module = cast(Any, import_module("kubernetes.config"))
        config_exception_module = cast(
            Any,
            import_module("kubernetes.config.config_exception"),
        )
        config_exception_type = cast(
            type[BaseException],
            config_exception_module.ConfigException,
        )
        try:
            config_module.load_incluster_config()
        except config_exception_type:
            kwargs: dict[str, object] = {}
            if self.kubeconfig_path is not None:
                kwargs["config_file"] = str(self.kubeconfig_path)
            if self.kube_context is not None:
                kwargs["context"] = self.kube_context
            config_module.load_kube_config(**kwargs)
        api_client = client_module.ApiClient()
        configuration = api_client.configuration
        loaded_host = getattr(configuration, "host", None)
        if isinstance(loaded_host, str) and loaded_host.strip():
            self.server_url = loaded_host.rstrip("/")
        self._core_api = cast(_CoreV1ApiLike, client_module.CoreV1Api(api_client))
        self._batch_api = cast(
            _BatchV1ApiLike,
            client_module.BatchV1Api(api_client),
        )
        self._rbac_api = cast(
            _RbacAuthorizationV1ApiLike,
            client_module.RbacAuthorizationV1Api(api_client),
        )
        self._networking_api = cast(
            _NetworkingV1ApiLike,
            client_module.NetworkingV1Api(api_client),
        )

    def _job_body(self, manifest: KubernetesJobManifest) -> dict[str, object]:
        labels = {
            **_normalize_metadata(manifest.tenant_boundary.labels),
            **_normalize_metadata(manifest.labels),
        }
        annotations = {
            **_normalize_metadata(manifest.tenant_boundary.annotations),
            **_normalize_metadata(manifest.annotations),
        }
        resources: dict[str, dict[str, str]] = {
            "requests": {
                "cpu": _cpu_quantity(manifest.resources.cpu_request_millis),
                "memory": _memory_quantity(manifest.resources.memory_request_mebibytes),
            },
            "limits": {
                "cpu": _cpu_quantity(manifest.resources.cpu_limit_millis),
                "memory": _memory_quantity(manifest.resources.memory_limit_mebibytes),
            },
        }
        if manifest.resources.ephemeral_storage_limit_mebibytes > 0:
            resources["limits"]["ephemeral-storage"] = _memory_quantity(
                manifest.resources.ephemeral_storage_limit_mebibytes
            )
        container: dict[str, object] = {
            "name": "agentsty-runner",
            "image": manifest.image_reference,
            "imagePullPolicy": manifest.image_pull_policy,
            "command": list(manifest.command),
            "args": list(manifest.args),
            "env": [
                {"name": key, "value": value} for key, value in manifest.environment
            ],
            "resources": resources,
            "securityContext": {
                "allowPrivilegeEscalation": (
                    manifest.isolation.allow_privilege_escalation
                ),
                "privileged": manifest.isolation.privileged,
                "readOnlyRootFilesystem": (
                    manifest.isolation.read_only_root_filesystem
                ),
            },
        }
        if manifest.volume_mounts:
            container["volumeMounts"] = [
                {
                    "name": mount.name,
                    "mountPath": mount.mount_path,
                    "readOnly": mount.read_only,
                }
                for mount in manifest.volume_mounts
            ]
        if manifest.working_directory is not None:
            container["workingDir"] = manifest.working_directory
        pod_spec: dict[str, object] = {
            "serviceAccountName": manifest.tenant_boundary.service_account_name,
            "automountServiceAccountToken": (
                manifest.isolation.automount_service_account_token
            ),
            "restartPolicy": "Never",
            "securityContext": {"runAsNonRoot": manifest.isolation.run_as_non_root},
            "containers": [container],
        }
        if manifest.volumes:
            pod_spec["volumes"] = [
                {
                    "name": volume.name,
                    "nfs": {
                        "server": volume.nfs.server,
                        "path": volume.nfs.path,
                        "readOnly": volume.nfs.read_only,
                    },
                }
                for volume in manifest.volumes
            ]
        if manifest.isolation.runtime_class_name is not None:
            pod_spec["runtimeClassName"] = manifest.isolation.runtime_class_name
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": manifest.job_name,
                "namespace": manifest.tenant_boundary.namespace,
                "labels": labels,
                "annotations": annotations,
            },
            "spec": {
                "backoffLimit": manifest.backoff_limit,
                "ttlSecondsAfterFinished": manifest.ttl_seconds_after_finished,
                "activeDeadlineSeconds": manifest.active_deadline_seconds,
                "template": {
                    "metadata": {
                        "labels": labels,
                        "annotations": annotations,
                    },
                    "spec": pod_spec,
                },
            },
        }

    def _observation_from_job(self, job: object) -> KubernetesJobObservation:
        metadata = _get_value(job, "metadata")
        spec = _get_value(job, "spec")
        status = _get_value(job, "status")
        template = _get_value(spec, "template")
        template_metadata = _get_value(template, "metadata")
        pod_spec = _get_value(template, "spec")
        containers = _list_items(_get_value(pod_spec, "containers"))
        container = containers[0] if containers else {}
        container_security = _get_value(container, "security_context") or _get_value(
            container, "securityContext"
        )
        pod_security = _get_value(pod_spec, "security_context") or _get_value(
            pod_spec, "securityContext"
        )
        annotations = {
            key: _string(value)
            for key, value in _mapping(_get_value(metadata, "annotations")).items()
        }
        labels = {
            key: _string(value)
            for key, value in _mapping(_get_value(metadata, "labels")).items()
        }
        requests = _get_value(_get_value(container, "resources"), "requests") or {}
        limits = _get_value(_get_value(container, "resources"), "limits") or {}
        manifest = KubernetesJobManifest(
            identity=cast(
                SandboxResourceIdentityLike,
                cast(object, _RestoredIdentity(_string(_get_value(metadata, "name")))),
            ),
            tenant_boundary=KubernetesTenantBoundary(
                namespace=_string(_get_value(metadata, "namespace")),
                service_account_name=_string(
                    _get_value(pod_spec, "service_account_name")
                    or _get_value(pod_spec, "serviceAccountName")
                ),
                labels=tuple((key, value) for key, value in labels.items()),
                annotations=tuple((key, value) for key, value in annotations.items()),
            ),
            job_name=_string(_get_value(metadata, "name")),
            image_reference=_string(_get_value(container, "image")),
            command=tuple(
                cast(list[str], _list_items(_get_value(container, "command")))
            ),
            args=tuple(cast(list[str], _list_items(_get_value(container, "args")))),
            environment=tuple(
                (
                    _string(_get_value(item, "name")),
                    _string(_get_value(item, "value")),
                )
                for item in _list_items(_get_value(container, "env"))
                if _string(_get_value(item, "name"))
            ),
            working_directory=cast(
                str | None,
                _get_value(container, "working_dir")
                or _get_value(container, "workingDir"),
            ),
            labels=tuple(
                (key, _string(value))
                for key, value in _mapping(
                    _get_value(template_metadata, "labels")
                ).items()
            ),
            annotations=tuple(
                (key, _string(value))
                for key, value in _mapping(
                    _get_value(template_metadata, "annotations")
                ).items()
            ),
            active_deadline_seconds=_int(
                _get_value(spec, "active_deadline_seconds")
                or _get_value(spec, "activeDeadlineSeconds"),
                default=900,
            ),
            ttl_seconds_after_finished=_int(
                _get_value(spec, "ttl_seconds_after_finished")
                or _get_value(spec, "ttlSecondsAfterFinished"),
                default=300,
            ),
            backoff_limit=_int(
                _get_value(spec, "backoff_limit") or _get_value(spec, "backoffLimit"),
                default=0,
            ),
            image_pull_policy=_string(
                _get_value(container, "image_pull_policy")
                or _get_value(container, "imagePullPolicy"),
                default="IfNotPresent",
            ),
            resources=KubernetesJobResources(
                cpu_request_millis=_parse_cpu_millis(
                    _mapping(requests).get("cpu"),
                    100,
                ),
                cpu_limit_millis=_parse_cpu_millis(_mapping(limits).get("cpu"), 100),
                memory_request_mebibytes=_parse_mebibytes(
                    _mapping(requests).get("memory"),
                    128,
                ),
                memory_limit_mebibytes=_parse_mebibytes(
                    _mapping(limits).get("memory"),
                    128,
                ),
                ephemeral_storage_limit_mebibytes=_parse_mebibytes(
                    _mapping(limits).get("ephemeral-storage"),
                    0,
                ),
            ),
            isolation=KubernetesJobIsolationSettings(
                runtime_class_name=cast(
                    str | None,
                    _get_value(pod_spec, "runtime_class_name")
                    or _get_value(pod_spec, "runtimeClassName"),
                ),
                require_kata_runtime=(
                    _get_value(pod_spec, "runtime_class_name")
                    or _get_value(pod_spec, "runtimeClassName")
                )
                is not None,
                automount_service_account_token=_bool(
                    _get_value(pod_spec, "automount_service_account_token")
                    or _get_value(pod_spec, "automountServiceAccountToken"),
                    default=False,
                ),
                run_as_non_root=_bool(
                    _get_value(pod_security, "run_as_non_root")
                    or _get_value(pod_security, "runAsNonRoot"),
                    default=True,
                ),
                read_only_root_filesystem=_bool(
                    _get_value(container_security, "read_only_root_filesystem")
                    or _get_value(container_security, "readOnlyRootFilesystem"),
                    default=True,
                ),
                allow_privilege_escalation=_bool(
                    _get_value(container_security, "allow_privilege_escalation")
                    or _get_value(container_security, "allowPrivilegeEscalation"),
                    default=False,
                ),
                privileged=_bool(
                    _get_value(container_security, "privileged"), default=False
                ),
            ),
            created_at=_datetime_from_value(
                _get_value(metadata, "creation_timestamp")
                or _get_value(metadata, "creationTimestamp")
            )
            or _utc_now(),
        )
        observed_at = _utc_now()
        started_at = _datetime_from_value(
            _get_value(status, "start_time") or _get_value(status, "startTime")
        )
        finished_at = _datetime_from_value(
            _get_value(status, "completion_time")
            or _get_value(status, "completionTime")
        )
        phase = KubernetesJobPhase.PENDING
        exit_code: int | None = None
        message = None
        error = None
        cancellation_requested_at = _datetime_from_value(
            annotations.get(_CANCELLATION_REQUESTED_AT)
        )
        if cancellation_requested_at is not None:
            phase = KubernetesJobPhase.CANCELLED
            finished_at = finished_at or cancellation_requested_at
            exit_code = 143
            message = annotations.get(_CANCELLATION_REASON)
        elif _int(_get_value(status, "succeeded"), 0) > 0:
            phase = KubernetesJobPhase.SUCCEEDED
            finished_at = finished_at or observed_at
            exit_code = 0
        else:
            failed_condition = self._failed_condition(status)
            if failed_condition is not None:
                message = cast(str | None, _get_value(failed_condition, "message"))
                reason = _string(_get_value(failed_condition, "reason"))
                if reason == "DeadlineExceeded":
                    phase = KubernetesJobPhase.TIMED_OUT
                    exit_code = 124
                else:
                    phase = KubernetesJobPhase.FAILED
                    exit_code = 1
                finished_at = finished_at or observed_at
            elif _int(_get_value(status, "active"), 0) > 0 or started_at is not None:
                phase = KubernetesJobPhase.RUNNING
            else:
                phase = KubernetesJobPhase.PENDING
        return KubernetesJobObservation(
            manifest=manifest,
            phase=phase,
            observed_at=observed_at,
            started_at=started_at,
            finished_at=finished_at,
            cancellation_requested_at=cancellation_requested_at,
            exit_code=exit_code,
            message=message,
            error=error,
        )

    def _failed_condition(self, status: object) -> object | None:
        conditions = _list_items(_get_value(status, "conditions"))
        for condition in conditions:
            if _string(_get_value(condition, "type")).lower() != "failed":
                continue
            condition_status = _string(_get_value(condition, "status")).lower()
            if condition_status in {"true", "1"}:
                return condition
        return None


@dataclass(frozen=True, slots=True)
class _RestoredIdentity:
    resource_name: str
    tenant_id: object = None
    request_id: object = None
    job_id: object = None


def profile_prefixes(settings: _SettingsLike) -> tuple[str, str]:
    profile = _profile_name(settings.profile)
    return (f"agentsty-{profile}", f"agentsty-{profile}-runner")

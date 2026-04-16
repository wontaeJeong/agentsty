"""Kubernetes Job executor package metadata and public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Final, cast

ConfiguredKubernetesControlPlane: object
InMemoryKubernetesControlPlane: object
KUBERNETES_EXECUTOR_NAME: object
KubernetesApiClient: object
KubernetesControlPlane: object
KubernetesJobExecutor: object
KubernetesJobExecutorSettings: object
KubernetesJobIsolationSettings: object
KubernetesJobManifest: object
KubernetesJobObservation: object
KubernetesJobPhase: object
KubernetesJobResources: object
KubernetesJobVolume: object
KubernetesNFSVolumeSource: object
KubernetesSharedStateMount: object
KubernetesTenantBoundary: object
KubernetesVolumeMount: object

__all__ = [
    "ConfiguredKubernetesControlPlane",
    "DISTRO_NAME",
    "InMemoryKubernetesControlPlane",
    "KUBERNETES_EXECUTOR_NAME",
    "KubernetesApiClient",
    "KubernetesControlPlane",
    "KubernetesJobExecutor",
    "KubernetesJobExecutorSettings",
    "KubernetesJobIsolationSettings",
    "KubernetesJobManifest",
    "KubernetesJobObservation",
    "KubernetesJobPhase",
    "KubernetesJobResources",
    "KubernetesJobVolume",
    "KubernetesNFSVolumeSource",
    "KubernetesSharedStateMount",
    "KubernetesTenantBoundary",
    "KubernetesVolumeMount",
    "PACKAGE_NAME",
    "PLATFORM_EXECUTOR_NAMESPACE",
    "__version__",
    "package_metadata",
]

PACKAGE_NAME: Final[str] = "agentsty_executor_kubernetes"
DISTRO_NAME: Final[str] = "agentsty-executor-kubernetes"
PLATFORM_EXECUTOR_NAMESPACE: Final[str] = "agentsty_platform.executors"
__version__: Final[str] = "0.0.0"


def package_metadata() -> dict[str, str]:
    """Return minimal executor package identity metadata."""

    return {
        "package_name": PACKAGE_NAME,
        "distribution_name": DISTRO_NAME,
        "platform_executor_namespace": PLATFORM_EXECUTOR_NAMESPACE,
        "version": __version__,
    }


def __getattr__(name: str) -> object:
    """Lazily expose executor symbols without eager package-local imports."""

    if name in {"KubernetesJobExecutor", "KUBERNETES_EXECUTOR_NAME"}:
        return cast(
            object,
            getattr(import_module("agentsty_executor_kubernetes.executor"), name),
        )
    if name in {"KubernetesControlPlane", "InMemoryKubernetesControlPlane"}:
        return cast(
            object,
            getattr(
                import_module("agentsty_executor_kubernetes.control_plane"),
                name,
            ),
        )
    if name == "ConfiguredKubernetesControlPlane":
        return cast(
            object,
            getattr(import_module("agentsty_executor_kubernetes.nonlocal"), name),
        )
    if name == "KubernetesApiClient":
        return cast(
            object,
            getattr(import_module("agentsty_executor_kubernetes.kube_client"), name),
        )
    if name in {
        "KubernetesJobExecutorSettings",
        "KubernetesJobIsolationSettings",
        "KubernetesJobManifest",
        "KubernetesJobObservation",
        "KubernetesJobPhase",
        "KubernetesJobResources",
        "KubernetesJobVolume",
        "KubernetesNFSVolumeSource",
        "KubernetesSharedStateMount",
        "KubernetesTenantBoundary",
        "KubernetesVolumeMount",
    }:
        return cast(
            object,
            getattr(import_module("agentsty_executor_kubernetes.models"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Real Kubernetes API-backed non-local control-plane composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast, override

from .control_plane import KubernetesControlPlane
from .kube_client import KubernetesApiClient
from .models import (
    KubernetesJobManifest,
    KubernetesJobObservation,
    KubernetesTenantBoundary,
)


class _ProfileValue(Protocol):
    value: str


class KubernetesApiClientLike(Protocol):
    server_url: str

    def ensure_namespace(self, boundary: KubernetesTenantBoundary) -> None: ...

    def create_job(self, manifest: KubernetesJobManifest) -> None: ...

    def read_job(
        self, namespace: str, job_name: str
    ) -> KubernetesJobObservation | None: ...

    def cancel_job(
        self,
        namespace: str,
        job_name: str,
        *,
        requested_at: datetime,
        reason: str | None = None,
        error: object | None = None,
    ) -> bool: ...

    def delete_job(self, namespace: str, job_name: str) -> bool: ...


@dataclass(slots=True)
class ConfiguredKubernetesControlPlane(KubernetesControlPlane):
    """Configured non-local control plane backed by the Kubernetes API client."""

    api_client: KubernetesApiClientLike
    api_server_url: str
    namespace_prefix: str
    service_account_prefix: str

    def __post_init__(self) -> None:
        self.api_server_url = self.api_server_url.rstrip("/")
        self.namespace_prefix = self.namespace_prefix.strip()
        self.service_account_prefix = self.service_account_prefix.strip()
        if not self.api_server_url.startswith("https://"):
            raise ValueError("api_server_url must use https")
        if not self.namespace_prefix:
            raise ValueError("namespace_prefix must not be empty")
        if not self.service_account_prefix:
            raise ValueError("service_account_prefix must not be empty")

    @classmethod
    def from_settings(
        cls,
        settings: object,
        *,
        api_client: KubernetesApiClientLike | None = None,
    ) -> ConfiguredKubernetesControlPlane:
        raw_profile = cast(Any, settings).profile
        profile = raw_profile if isinstance(raw_profile, str) else raw_profile.value
        resolved_client = (
            api_client
            if api_client is not None
            else cast(
                KubernetesApiClientLike,
                KubernetesApiClient.from_settings(cast(Any, settings)),
            )
        )
        return cls(
            api_client=resolved_client,
            api_server_url=resolved_client.server_url,
            namespace_prefix=f"agentsty-{profile}",
            service_account_prefix=f"agentsty-{profile}-runner",
        )

    @override
    def ensure_namespace(self, boundary: KubernetesTenantBoundary) -> None:
        self.api_client.ensure_namespace(boundary)

    @override
    def create_job(self, manifest: KubernetesJobManifest) -> None:
        self.api_client.create_job(manifest)

    @override
    def read_job(
        self, namespace: str, job_name: str
    ) -> KubernetesJobObservation | None:
        return self.api_client.read_job(namespace, job_name)

    @override
    def cancel_job(
        self,
        namespace: str,
        job_name: str,
        *,
        requested_at: datetime,
        reason: str | None = None,
        error: object | None = None,
    ) -> bool:
        return self.api_client.cancel_job(
            namespace,
            job_name,
            requested_at=requested_at,
            reason=reason,
            error=error,
        )

    @override
    def delete_job(self, namespace: str, job_name: str) -> bool:
        return self.api_client.delete_job(namespace, job_name)

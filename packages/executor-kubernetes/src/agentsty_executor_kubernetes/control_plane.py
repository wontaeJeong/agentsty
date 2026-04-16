"""Local Kubernetes control-plane test double and protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from .models import (
    KubernetesJobManifest,
    KubernetesJobObservation,
    KubernetesJobPhase,
    KubernetesTenantBoundary,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class KubernetesControlPlane(Protocol):
    """Minimal control-plane seam used by the Kubernetes Job executor."""

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
class InMemoryKubernetesControlPlane:
    """Stateful local control-plane double for executor tests and smoke checks."""

    namespaces: dict[str, KubernetesTenantBoundary] = field(default_factory=dict)
    resource_quotas: dict[str, str] = field(default_factory=dict)
    limit_ranges: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    role_bindings: dict[str, str] = field(default_factory=dict)
    network_policies: dict[str, str] = field(default_factory=dict)
    jobs: dict[tuple[str, str], KubernetesJobObservation] = field(default_factory=dict)

    def ensure_namespace(self, boundary: KubernetesTenantBoundary) -> None:
        self.namespaces[boundary.namespace] = boundary
        self.resource_quotas[boundary.namespace] = "tenant-sandbox-quota"
        self.limit_ranges[boundary.namespace] = "tenant-sandbox-limits"
        self.roles[boundary.namespace] = "agentsty-sandbox-runner"
        self.role_bindings[boundary.namespace] = "agentsty-sandbox-runner"
        self.network_policies[boundary.namespace] = "tenant-sandbox-default-deny"

    def create_job(self, manifest: KubernetesJobManifest) -> None:
        if manifest.tenant_boundary.namespace not in self.namespaces:
            raise ValueError("namespace must exist before creating a job")
        key = (manifest.tenant_boundary.namespace, manifest.job_name)
        if key in self.jobs:
            raise ValueError("job already exists")
        self.jobs[key] = KubernetesJobObservation(
            manifest=manifest,
            phase=KubernetesJobPhase.PENDING,
        )

    def read_job(
        self, namespace: str, job_name: str
    ) -> KubernetesJobObservation | None:
        return self.jobs.get((namespace, job_name))

    def cancel_job(
        self,
        namespace: str,
        job_name: str,
        *,
        requested_at: datetime,
        reason: str | None = None,
        error: object | None = None,
    ) -> bool:
        key = (namespace, job_name)
        observation = self.jobs.get(key)
        if observation is None:
            return False
        if observation.phase.is_terminal:
            return False
        self.jobs[key] = observation.with_phase(
            KubernetesJobPhase.CANCELLED,
            observed_at=requested_at,
            started_at=observation.started_at,
            finished_at=requested_at,
            cancellation_requested_at=requested_at,
            exit_code=143,
            message=reason,
            error=error,
        )
        return True

    def delete_job(self, namespace: str, job_name: str) -> bool:
        return self.jobs.pop((namespace, job_name), None) is not None

    def mark_running(
        self,
        namespace: str,
        job_name: str,
        *,
        started_at: datetime | None = None,
    ) -> None:
        key = (namespace, job_name)
        observation = self.jobs[key]
        self.jobs[key] = observation.with_phase(
            KubernetesJobPhase.RUNNING,
            observed_at=started_at or _utc_now(),
            started_at=started_at or _utc_now(),
        )

    def mark_succeeded(
        self,
        namespace: str,
        job_name: str,
        *,
        finished_at: datetime | None = None,
        exit_code: int = 0,
    ) -> None:
        key = (namespace, job_name)
        observation = self.jobs[key]
        completed_at = finished_at or _utc_now()
        self.jobs[key] = observation.with_phase(
            KubernetesJobPhase.SUCCEEDED,
            observed_at=completed_at,
            started_at=observation.started_at or completed_at,
            finished_at=completed_at,
            exit_code=exit_code,
        )

    def mark_failed(
        self,
        namespace: str,
        job_name: str,
        *,
        message: str,
        finished_at: datetime | None = None,
        exit_code: int = 1,
        error: object | None = None,
    ) -> None:
        key = (namespace, job_name)
        observation = self.jobs[key]
        completed_at = finished_at or _utc_now()
        self.jobs[key] = observation.with_phase(
            KubernetesJobPhase.FAILED,
            observed_at=completed_at,
            started_at=observation.started_at or completed_at,
            finished_at=completed_at,
            exit_code=exit_code,
            message=message,
            error=error,
        )

    def mark_timed_out(
        self,
        namespace: str,
        job_name: str,
        *,
        message: str,
        finished_at: datetime | None = None,
        error: object | None = None,
    ) -> None:
        key = (namespace, job_name)
        observation = self.jobs[key]
        completed_at = finished_at or _utc_now()
        self.jobs[key] = observation.with_phase(
            KubernetesJobPhase.TIMED_OUT,
            observed_at=completed_at,
            started_at=observation.started_at or completed_at,
            finished_at=completed_at,
            exit_code=124,
            message=message,
            error=error,
        )

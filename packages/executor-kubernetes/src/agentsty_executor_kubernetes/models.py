"""Kubernetes Job executor models and local manifest representations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _normalize_required(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _normalize_optional(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


Metadata = tuple[tuple[str, str], ...]


def _normalize_path(name: str, value: str) -> str:
    normalized = _normalize_required(name, value)
    if not normalized.startswith("/"):
        raise ValueError(f"{name} must be an absolute path")
    return normalized.rstrip("/") or "/"


@dataclass(frozen=True, slots=True)
class KubernetesNFSVolumeSource:
    """NFS-backed shared volume source for cross-namespace runtime handoff."""

    server: str
    path: str
    read_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "server", _normalize_required("server", self.server))
        object.__setattr__(self, "path", _normalize_path("path", self.path))


@dataclass(frozen=True, slots=True)
class KubernetesJobVolume:
    """Volume definition attached to rendered Kubernetes Job manifests."""

    name: str
    nfs: KubernetesNFSVolumeSource

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_required("name", self.name))


@dataclass(frozen=True, slots=True)
class KubernetesVolumeMount:
    """Container volume mount attached to rendered Kubernetes Job manifests."""

    name: str
    mount_path: str
    read_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_required("name", self.name))
        object.__setattr__(
            self, "mount_path", _normalize_path("mount_path", self.mount_path)
        )


@dataclass(frozen=True, slots=True)
class KubernetesSharedStateMount:
    """Shared runtime-state volume mounted into sandbox Jobs."""

    volume: KubernetesJobVolume
    mounts: tuple[KubernetesVolumeMount, ...]

    def __post_init__(self) -> None:
        mounts = tuple(self.mounts)
        if not mounts:
            raise ValueError("mounts must not be empty")
        for mount in mounts:
            if mount.name != self.volume.name:
                raise ValueError(
                    "shared-state mounts must reference the shared-state volume"
                )
        object.__setattr__(self, "mounts", mounts)


def _normalize_metadata(metadata: Metadata) -> Metadata:
    normalized: list[tuple[str, str]] = []
    for key, value in metadata:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("metadata keys must not be empty")
        normalized.append((clean_key, value))
    return tuple(normalized)


class SandboxResourceIdentityLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    resource_name: str


@dataclass(frozen=True, slots=True)
class KubernetesTenantBoundary:
    """Tenant namespace and service account boundary for a Job sandbox."""

    namespace: str
    service_account_name: str
    labels: Metadata = field(default_factory=tuple)
    annotations: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "namespace", _normalize_required("namespace", self.namespace)
        )
        object.__setattr__(
            self,
            "service_account_name",
            _normalize_required("service_account_name", self.service_account_name),
        )
        object.__setattr__(self, "labels", _normalize_metadata(self.labels))
        object.__setattr__(self, "annotations", _normalize_metadata(self.annotations))


@dataclass(frozen=True, slots=True)
class KubernetesJobResources:
    """Kubernetes request/limit resource profile for a sandbox Job."""

    cpu_request_millis: int
    cpu_limit_millis: int
    memory_request_mebibytes: int
    memory_limit_mebibytes: int
    ephemeral_storage_limit_mebibytes: int = 0

    def __post_init__(self) -> None:
        if self.cpu_request_millis < 1:
            raise ValueError("cpu_request_millis must be at least 1")
        if self.cpu_limit_millis < self.cpu_request_millis:
            raise ValueError("cpu_limit_millis must be >= cpu_request_millis")
        if self.memory_request_mebibytes < 1:
            raise ValueError("memory_request_mebibytes must be at least 1")
        if self.memory_limit_mebibytes < self.memory_request_mebibytes:
            raise ValueError(
                "memory_limit_mebibytes must be >= memory_request_mebibytes"
            )
        if self.ephemeral_storage_limit_mebibytes < 0:
            raise ValueError("ephemeral_storage_limit_mebibytes must not be negative")


@dataclass(frozen=True, slots=True)
class KubernetesJobIsolationSettings:
    """Isolation and pod security posture for Kubernetes Job sandboxes."""

    runtime_class_name: str | None = "kata-clh"
    require_kata_runtime: bool = True
    automount_service_account_token: bool = False
    run_as_non_root: bool = True
    read_only_root_filesystem: bool = True
    allow_privilege_escalation: bool = False
    privileged: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_class_name",
            _normalize_optional("runtime_class_name", self.runtime_class_name),
        )
        if self.require_kata_runtime and self.runtime_class_name is None:
            raise ValueError(
                "runtime_class_name is required when require_kata_runtime is enabled"
            )
        if self.allow_privilege_escalation:
            raise ValueError("allow_privilege_escalation must remain disabled")
        if self.privileged:
            raise ValueError("privileged containers must remain disabled")
        if not self.run_as_non_root:
            raise ValueError("run_as_non_root must remain enabled")
        if not self.read_only_root_filesystem:
            raise ValueError("read_only_root_filesystem must remain enabled")


@dataclass(frozen=True, slots=True)
class KubernetesJobExecutorSettings:
    """Kubernetes Job naming and lifecycle defaults for executor instances."""

    namespace_prefix: str = "agentsty-"
    job_name_prefix: str = "sandbox-"
    image_pull_policy: str = "IfNotPresent"
    backoff_limit: int = 0
    ttl_seconds_after_finished: int = 300

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "namespace_prefix",
            _normalize_required("namespace_prefix", self.namespace_prefix),
        )
        object.__setattr__(
            self,
            "job_name_prefix",
            _normalize_required("job_name_prefix", self.job_name_prefix),
        )
        object.__setattr__(
            self,
            "image_pull_policy",
            _normalize_required("image_pull_policy", self.image_pull_policy),
        )
        if self.backoff_limit < 0:
            raise ValueError("backoff_limit must not be negative")
        if self.ttl_seconds_after_finished < 0:
            raise ValueError("ttl_seconds_after_finished must not be negative")


@dataclass(frozen=True, slots=True)
class KubernetesJobManifest:
    """Rendered Kubernetes Job manifest representation used by the executor."""

    identity: SandboxResourceIdentityLike
    tenant_boundary: KubernetesTenantBoundary
    job_name: str
    image_reference: str
    command: tuple[str, ...]
    args: tuple[str, ...] = ()
    environment: Metadata = field(default_factory=tuple)
    volume_mounts: tuple[KubernetesVolumeMount, ...] = field(default_factory=tuple)
    volumes: tuple[KubernetesJobVolume, ...] = field(default_factory=tuple)
    working_directory: str | None = None
    labels: Metadata = field(default_factory=tuple)
    annotations: Metadata = field(default_factory=tuple)
    active_deadline_seconds: int = 900
    ttl_seconds_after_finished: int = 300
    backoff_limit: int = 0
    image_pull_policy: str = "IfNotPresent"
    resources: KubernetesJobResources = field(
        default_factory=lambda: KubernetesJobResources(
            cpu_request_millis=100,
            cpu_limit_millis=100,
            memory_request_mebibytes=128,
            memory_limit_mebibytes=128,
        )
    )
    isolation: KubernetesJobIsolationSettings = field(
        default_factory=KubernetesJobIsolationSettings
    )
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "job_name", _normalize_required("job_name", self.job_name)
        )
        object.__setattr__(
            self,
            "image_reference",
            _normalize_required("image_reference", self.image_reference),
        )
        command = tuple(item.strip() for item in self.command if item.strip())
        if not command:
            raise ValueError("command must not be empty")
        object.__setattr__(self, "command", command)
        object.__setattr__(
            self, "args", tuple(item.strip() for item in self.args if item.strip())
        )
        object.__setattr__(self, "environment", _normalize_metadata(self.environment))
        object.__setattr__(self, "volume_mounts", tuple(self.volume_mounts))
        object.__setattr__(self, "volumes", tuple(self.volumes))
        object.__setattr__(self, "labels", _normalize_metadata(self.labels))
        object.__setattr__(self, "annotations", _normalize_metadata(self.annotations))
        object.__setattr__(
            self,
            "working_directory",
            _normalize_optional("working_directory", self.working_directory),
        )
        if self.active_deadline_seconds < 1:
            raise ValueError("active_deadline_seconds must be at least 1")
        if self.ttl_seconds_after_finished < 0:
            raise ValueError("ttl_seconds_after_finished must not be negative")
        if self.backoff_limit < 0:
            raise ValueError("backoff_limit must not be negative")
        object.__setattr__(
            self,
            "image_pull_policy",
            _normalize_required("image_pull_policy", self.image_pull_policy),
        )
        _require_aware_datetime("created_at", self.created_at)


class KubernetesJobPhase(StrEnum):
    """Local phase model used for Kubernetes Job status inspection."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.TIMED_OUT, self.CANCELLED}


@dataclass(frozen=True, slots=True)
class KubernetesJobObservation:
    """Latest observed Job state returned by a control-plane adapter."""

    manifest: KubernetesJobManifest
    phase: KubernetesJobPhase
    observed_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    exit_code: int | None = None
    message: str | None = None
    error: object | None = None

    def __post_init__(self) -> None:
        _require_aware_datetime("observed_at", self.observed_at)
        if self.started_at is not None:
            _require_aware_datetime("started_at", self.started_at)
        if self.finished_at is not None:
            _require_aware_datetime("finished_at", self.finished_at)
        if self.cancellation_requested_at is not None:
            _require_aware_datetime(
                "cancellation_requested_at", self.cancellation_requested_at
            )
        object.__setattr__(
            self, "message", _normalize_optional("message", self.message)
        )
        if self.phase.is_terminal and self.finished_at is None:
            raise ValueError("terminal job observations must include finished_at")
        if not self.phase.is_terminal and self.finished_at is not None:
            raise ValueError(
                "non-terminal job observations must not include finished_at"
            )
        if self.phase == KubernetesJobPhase.RUNNING and self.started_at is None:
            raise ValueError("running job observations must include started_at")

    def with_phase(
        self,
        phase: KubernetesJobPhase,
        *,
        observed_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        cancellation_requested_at: datetime | None = None,
        exit_code: int | None = None,
        message: str | None = None,
        error: object | None = None,
    ) -> KubernetesJobObservation:
        return replace(
            self,
            phase=phase,
            observed_at=observed_at or _utc_now(),
            started_at=started_at if started_at is not None else self.started_at,
            finished_at=finished_at,
            cancellation_requested_at=(
                cancellation_requested_at
                if cancellation_requested_at is not None
                else self.cancellation_requested_at
            ),
            exit_code=exit_code,
            message=message,
            error=error,
        )

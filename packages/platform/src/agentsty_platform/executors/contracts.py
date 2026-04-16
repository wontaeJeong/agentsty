"""Shared sandbox executor lifecycle contracts independent of any backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..domain.errors import ErrorCategory, ErrorDetails
from ..domain.ids import JobId, RequestId, TenantId
from ..domain.models import ExecutionTimeouts, Metadata, normalize_metadata


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


def _normalize_command(name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(item.strip() for item in value if item.strip())
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


class SandboxIsolationMode(StrEnum):
    """Isolation level requested from a sandbox executor."""

    PROCESS = "process"
    CONTAINER = "container"
    VIRTUAL_MACHINE = "virtual_machine"


class SandboxStatus(StrEnum):
    """Stable sandbox lifecycle states independent of any backend."""

    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.TIMED_OUT,
            self.CANCELLED,
        }


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    """Stable capability summary for pluggable sandbox executors."""

    supported_isolation_modes: tuple[SandboxIsolationMode, ...] = (
        SandboxIsolationMode.CONTAINER,
    )
    tenant_boundary_kind: str = "scope"
    supports_status_inspection: bool = True
    supports_cancellation: bool = True
    supports_cleanup: bool = True
    supports_separate_launch_phase: bool = True

    def __post_init__(self) -> None:
        if not self.supported_isolation_modes:
            raise ValueError("supported_isolation_modes must not be empty")
        object.__setattr__(
            self,
            "tenant_boundary_kind",
            _normalize_required("tenant_boundary_kind", self.tenant_boundary_kind),
        )


@dataclass(frozen=True, slots=True)
class TenantResourceBoundary:
    """Tenant-scoped boundary that contains executor-managed resources."""

    tenant_id: TenantId
    boundary_kind: str
    boundary_name: str
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "boundary_kind",
            _normalize_required("boundary_kind", self.boundary_kind),
        )
        object.__setattr__(
            self,
            "boundary_name",
            _normalize_required("boundary_name", self.boundary_name),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxProgramSpec:
    """Portable execution entrypoint description for a sandbox."""

    command: tuple[str, ...]
    args: tuple[str, ...] = ()
    environment: Metadata = field(default_factory=tuple)
    working_directory: str | None = None
    image_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _normalize_command("command", self.command))
        object.__setattr__(
            self, "args", tuple(item.strip() for item in self.args if item.strip())
        )
        object.__setattr__(self, "environment", normalize_metadata(self.environment))
        object.__setattr__(
            self,
            "working_directory",
            _normalize_optional("working_directory", self.working_directory),
        )
        object.__setattr__(
            self,
            "image_reference",
            _normalize_optional("image_reference", self.image_reference),
        )


@dataclass(frozen=True, slots=True)
class SandboxResourceRequirements:
    """Portable resource budget for a sandbox execution."""

    cpu_millis: int
    memory_mebibytes: int
    ephemeral_storage_mebibytes: int = 0

    def __post_init__(self) -> None:
        if self.cpu_millis < 1:
            raise ValueError("cpu_millis must be at least 1")
        if self.memory_mebibytes < 1:
            raise ValueError("memory_mebibytes must be at least 1")
        if self.ephemeral_storage_mebibytes < 0:
            raise ValueError("ephemeral_storage_mebibytes must not be negative")


@dataclass(frozen=True, slots=True)
class SandboxResourceIdentity:
    """Stable identity for an executor-managed tenant-scoped resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    executor_name: str
    provider: str
    resource_kind: str
    resource_name: str
    boundary: TenantResourceBoundary
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox resource tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox resource tenant")
        if self.boundary.tenant_id != self.tenant_id:
            raise ValueError(
                "sandbox resource boundary tenant must match resource tenant"
            )
        object.__setattr__(
            self,
            "executor_name",
            _normalize_required("executor_name", self.executor_name),
        )
        object.__setattr__(
            self, "provider", _normalize_required("provider", self.provider)
        )
        object.__setattr__(
            self,
            "resource_kind",
            _normalize_required("resource_kind", self.resource_kind),
        )
        object.__setattr__(
            self,
            "resource_name",
            _normalize_required("resource_name", self.resource_name),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxCreateRequest:
    """Create-time input for provisioning a tenant-scoped sandbox resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    program: SandboxProgramSpec
    resources: SandboxResourceRequirements
    timeouts: ExecutionTimeouts = field(default_factory=ExecutionTimeouts)
    desired_isolation: SandboxIsolationMode = SandboxIsolationMode.CONTAINER
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox create tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox create tenant")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxHandle:
    """Created sandbox resource ready to be launched and inspected."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    executor_name: str
    identity: SandboxResourceIdentity
    program: SandboxProgramSpec
    resources: SandboxResourceRequirements
    timeouts: ExecutionTimeouts
    desired_isolation: SandboxIsolationMode
    created_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox handle tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox handle tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match sandbox handle tenant")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match sandbox handle")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match sandbox handle")
        _require_aware_datetime("created_at", self.created_at)
        object.__setattr__(
            self,
            "executor_name",
            _normalize_required("executor_name", self.executor_name),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxLaunchRequest:
    """Launch intent for a created sandbox resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox launch tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox launch tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match launch tenant")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match launch request")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match launch request")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxLaunchReceipt:
    """Acknowledgement that an executor accepted a sandbox launch."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    accepted_at: datetime = field(default_factory=_utc_now)
    deadline_at: datetime | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox launch tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox launch tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match launch receipt")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match launch receipt")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match launch receipt")
        _require_aware_datetime("accepted_at", self.accepted_at)
        if self.deadline_at is not None:
            _require_aware_datetime("deadline_at", self.deadline_at)
            if self.deadline_at < self.accepted_at:
                raise ValueError("deadline_at must not be earlier than accepted_at")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxInspection:
    """Latest observed sandbox status for one tenant-scoped execution resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    status: SandboxStatus
    observed_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    deadline_at: datetime | None = None
    exit_code: int | None = None
    error: ErrorDetails | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox inspection tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox inspection tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match inspection tenant")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match inspection")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match inspection")
        _require_aware_datetime("observed_at", self.observed_at)
        if self.started_at is not None:
            _require_aware_datetime("started_at", self.started_at)
        if self.finished_at is not None:
            _require_aware_datetime("finished_at", self.finished_at)
            if (
                self.finished_at < self.observed_at
                and self.status == SandboxStatus.CREATED
            ):
                raise ValueError("created sandboxes must not include finished_at")
        if self.cancellation_requested_at is not None:
            _require_aware_datetime(
                "cancellation_requested_at", self.cancellation_requested_at
            )
        if self.deadline_at is not None:
            _require_aware_datetime("deadline_at", self.deadline_at)
        if self.status.is_terminal and self.finished_at is None:
            raise ValueError("terminal sandbox inspections must include finished_at")
        if not self.status.is_terminal and self.finished_at is not None:
            raise ValueError(
                "non-terminal sandbox inspections must not include finished_at"
            )
        if self.status in {SandboxStatus.RUNNING, SandboxStatus.CANCELLING}:
            if self.started_at is None:
                raise ValueError(
                    f"{self.status.value} inspections must include started_at"
                )
        if (
            self.status
            in {
                SandboxStatus.FAILED,
                SandboxStatus.TIMED_OUT,
                SandboxStatus.CANCELLED,
            }
            and self.error is None
        ):
            raise ValueError(f"{self.status.value} inspections must include an error")
        if (
            self.status == SandboxStatus.TIMED_OUT
            and self.error is not None
            and self.error.category != ErrorCategory.TIMEOUT
        ):
            raise ValueError("timed out sandboxes must use timeout error details")
        if (
            self.status == SandboxStatus.CANCELLED
            and self.error is not None
            and self.error.category != ErrorCategory.CANCELLATION
        ):
            raise ValueError("cancelled sandboxes must use cancellation error details")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxCancellationRequest:
    """Cancellation intent for a created or running sandbox resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    reason: str | None = None
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox cancellation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox cancellation tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match cancellation tenant")
        if self.identity.request_id != self.request_id:
            raise ValueError(
                "sandbox identity request id must match cancellation request"
            )
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match cancellation request")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "reason", _normalize_optional("reason", self.reason))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxCancellationReceipt:
    """Acknowledgement of sandbox cancellation intent."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    acknowledged: bool
    requested_at: datetime = field(default_factory=_utc_now)
    error: ErrorDetails | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox cancellation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox cancellation tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match cancellation receipt")
        if self.identity.request_id != self.request_id:
            raise ValueError(
                "sandbox identity request id must match cancellation receipt"
            )
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match cancellation receipt")
        _require_aware_datetime("requested_at", self.requested_at)
        if not self.acknowledged and self.error is None:
            raise ValueError(
                "non-acknowledged sandbox cancellation receipts must include an error"
            )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxCleanupRequest:
    """Cleanup request for a created or completed sandbox resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox cleanup tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox cleanup tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match cleanup tenant")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match cleanup request")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match cleanup request")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SandboxCleanupResult:
    """Cleanup outcome for a sandbox resource."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    identity: SandboxResourceIdentity
    cleaned: bool
    cleaned_at: datetime = field(default_factory=_utc_now)
    released_resources: tuple[str, ...] = ()
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match sandbox cleanup tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match sandbox cleanup tenant")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("sandbox identity tenant must match cleanup result")
        if self.identity.request_id != self.request_id:
            raise ValueError("sandbox identity request id must match cleanup result")
        if self.identity.job_id != self.job_id:
            raise ValueError("sandbox identity job id must match cleanup result")
        _require_aware_datetime("cleaned_at", self.cleaned_at)
        object.__setattr__(
            self,
            "released_resources",
            tuple(item.strip() for item in self.released_resources if item.strip()),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


def status_for_error(error: ErrorDetails) -> SandboxStatus:
    """Map shared error details to a terminal sandbox status."""

    if error.category is ErrorCategory.TIMEOUT:
        return SandboxStatus.TIMED_OUT
    if error.category is ErrorCategory.CANCELLATION:
        return SandboxStatus.CANCELLED
    return SandboxStatus.FAILED

"""Shared agent runtime lifecycle contracts independent of any executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from ..domain.errors import ErrorCategory, ErrorDetails
from ..domain.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from ..domain.ids import JobId, RequestId, TenantId
from ..domain.models import Metadata, normalize_metadata
from ..gateway.contracts import GatewayRequest, GatewayResponse
from ..observability.tracing import TraceContext


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _normalize_optional(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} must not be blank")
    return cleaned


class RuntimeAutomationMode(StrEnum):
    """Automation mode exposed by a runtime adapter."""

    HEADLESS = "headless"


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    """Stable capability summary for pluggable runtime adapters."""

    automation_mode: RuntimeAutomationMode = RuntimeAutomationMode.HEADLESS
    uses_internal_gateway: bool = True
    supports_result_collection: bool = True
    supports_cancellation: bool = True
    supports_cleanup: bool = True


@dataclass(frozen=True, slots=True)
class RuntimePreparationRequest:
    """Preparation input for creating a runtime session workspace."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    workspace_path: Path
    trace_context: TraceContext | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime preparation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime preparation tenant")
        if str(self.workspace_path).strip() == "":
            raise ValueError("workspace_path must not be empty")
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError(
                    "trace context tenant must match runtime preparation tenant"
                )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeSession:
    """Prepared runtime session bound to one tenant-scoped execution."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    runtime_name: str
    session_id: str
    workspace_path: Path
    capabilities: RuntimeCapabilities = field(default_factory=RuntimeCapabilities)
    prepared_at: datetime = field(default_factory=_utc_now)
    trace_context: TraceContext | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime session tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime session tenant")
        if not self.runtime_name.strip():
            raise ValueError("runtime_name must not be empty")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if str(self.workspace_path).strip() == "":
            raise ValueError("workspace_path must not be empty")
        _require_aware_datetime("prepared_at", self.prepared_at)
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError(
                    "trace context tenant must match runtime session tenant"
                )
        object.__setattr__(self, "runtime_name", self.runtime_name.strip())
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeInvocationRequest:
    """Invocation input that composes the shared execution and gateway contracts."""

    execution: ExecutionRequest[GatewayRequest]
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeInvocationReceipt:
    """Acknowledgement that a runtime accepted an invocation for execution."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    accepted_at: datetime = field(default_factory=_utc_now)
    automation_mode: RuntimeAutomationMode = RuntimeAutomationMode.HEADLESS
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime invocation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime invocation tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("accepted_at", self.accepted_at)
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCollectionRequest:
    """Request to collect the latest terminal outcome for a runtime session."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime collection tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime collection tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCollectionResult:
    """Result-collection status for a runtime session."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    ready: bool
    result: ExecutionResult[GatewayResponse] | None = None
    collected_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime collection tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime collection tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("collected_at", self.collected_at)
        if self.ready and self.result is None:
            raise ValueError("ready runtime collection results must include a result")
        if not self.ready and self.result is not None:
            raise ValueError(
                "non-ready runtime collection results must not include a result"
            )
        if self.result is not None:
            if self.result.tenant_id != self.tenant_id:
                raise ValueError("result tenant must match runtime collection tenant")
            if self.result.request_id != self.request_id:
                raise ValueError(
                    "result request id must match runtime collection request id"
                )
            if self.result.job_id != self.job_id:
                raise ValueError("result job id must match runtime collection job id")
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCancellationRequest:
    """Cancellation intent for a prepared runtime session."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    reason: str | None = None
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime cancellation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime cancellation tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "reason", _normalize_optional("reason", self.reason))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCancellationReceipt:
    """Acknowledgement of a runtime cancellation intent."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    acknowledged: bool
    requested_at: datetime = field(default_factory=_utc_now)
    error: ErrorDetails | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime cancellation tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime cancellation tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("requested_at", self.requested_at)
        if not self.acknowledged and self.error is None:
            raise ValueError(
                "non-acknowledged runtime cancellation receipts must include an error"
            )
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCleanupRequest:
    """Cleanup request for a prepared runtime session."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    requested_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime cleanup tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime cleanup tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("requested_at", self.requested_at)
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeCleanupResult:
    """Cleanup outcome for a runtime session."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    session_id: str
    cleaned: bool
    cleaned_at: datetime = field(default_factory=_utc_now)
    released_paths: tuple[str, ...] = ()
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match runtime cleanup tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match runtime cleanup tenant")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        _require_aware_datetime("cleaned_at", self.cleaned_at)
        object.__setattr__(self, "session_id", self.session_id.strip())
        object.__setattr__(
            self,
            "released_paths",
            tuple(path.strip() for path in self.released_paths if path.strip()),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


def status_for_error(error: ErrorDetails) -> ExecutionStatus:
    """Map shared error details to a terminal execution status."""

    if error.category is ErrorCategory.TIMEOUT:
        return ExecutionStatus.TIMED_OUT
    if error.category is ErrorCategory.CANCELLATION:
        return ExecutionStatus.CANCELLED
    return ExecutionStatus.FAILED

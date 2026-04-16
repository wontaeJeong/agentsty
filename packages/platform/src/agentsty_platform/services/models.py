"""Transport-agnostic request and result models for orchestration services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..domain.ids import IdempotencyKey, JobId, RequestId, TenantId
from ..domain.models import ExecutionTimeouts, Metadata, normalize_metadata
from ..executors.contracts import (
    SandboxIsolationMode,
    SandboxProgramSpec,
    SandboxResourceRequirements,
)
from ..gateway.contracts import GatewayRequest, GatewayResponse
from ..observability.tracing import TraceContext
from ..persistence.models import AuditMetadata, JobRecord


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExecutionSubmitRequest:
    """Input contract for submitting one tenant-scoped execution request."""

    tenant_id: TenantId
    idempotency_key: IdempotencyKey
    gateway_request: GatewayRequest
    sandbox_program: SandboxProgramSpec
    sandbox_resources: SandboxResourceRequirements
    request_id: RequestId | None = None
    job_id: JobId | None = None
    timeouts: ExecutionTimeouts = field(default_factory=ExecutionTimeouts)
    desired_isolation: SandboxIsolationMode = SandboxIsolationMode.CONTAINER
    trace_context: TraceContext | None = None
    audit_metadata: AuditMetadata = field(
        default_factory=lambda: AuditMetadata(source="services.request_intake")
    )
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.gateway_request.tenant_id != self.tenant_id:
            raise ValueError("gateway request tenant must match service request tenant")
        if self.request_id is not None and self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match service request tenant")
        if self.job_id is not None and self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match service request tenant")
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError(
                    "trace context tenant must match service request tenant"
                )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ExecutionSubmitResult:
    """Submission result returned by the orchestration public API."""

    job: JobRecord[GatewayRequest, GatewayResponse]
    trace_context: TraceContext
    idempotent_replay: bool = False
    cleanup_performed: bool = False
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.job.tenant_id:
                raise ValueError(
                    "trace context tenant must match submission result tenant"
                )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ExecutionPollResult:
    """Status lookup or lifecycle advancement result for an execution."""

    job: JobRecord[GatewayRequest, GatewayResponse]
    cleanup_performed: bool = False
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ExecutionCancellationRequest:
    """Cancellation intent for a tenant-scoped execution."""

    tenant_id: TenantId
    job_id: JobId
    reason: str | None = None
    requested_at: datetime = field(default_factory=_utc_now)
    trace_context: TraceContext | None = None
    audit_metadata: AuditMetadata = field(
        default_factory=lambda: AuditMetadata(source="services.cancellation")
    )
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match cancellation tenant")
        _require_aware_datetime("requested_at", self.requested_at)
        clean_reason = None if self.reason is None else self.reason.strip()
        if clean_reason == "":
            raise ValueError("cancellation reason must not be blank")
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError("trace context tenant must match cancellation tenant")
        object.__setattr__(self, "reason", clean_reason)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ExecutionCancellationResult:
    """Cancellation result returned by the orchestration public API."""

    job: JobRecord[GatewayRequest, GatewayResponse]
    cancellation_requested: bool
    cleanup_performed: bool = False
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

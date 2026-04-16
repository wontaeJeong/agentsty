"""Persistence records shared across repository and storage implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, TypeVar

from ..domain.errors import ErrorDetails
from ..domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
)
from ..domain.ids import IdempotencyKey, JobId, RequestId, TenantId
from ..domain.models import ArtifactSummary, Metadata, ResultSummary, normalize_metadata

RequestPayloadT = TypeVar("RequestPayloadT")
ResultPayloadT = TypeVar("ResultPayloadT")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AuditMetadata:
    """Stable audit context attached to lifecycle and idempotency events."""

    actor: str | None = None
    source: str = "system"
    correlation_id: str | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_source = self.source.strip()
        if not clean_source:
            raise ValueError("audit source must not be empty")
        clean_actor = None if self.actor is None else self.actor.strip()
        if clean_actor == "":
            raise ValueError("audit actor must not be blank")
        clean_correlation_id = (
            None if self.correlation_id is None else self.correlation_id.strip()
        )
        if clean_correlation_id == "":
            raise ValueError("audit correlation id must not be blank")
        object.__setattr__(self, "source", clean_source)
        object.__setattr__(self, "actor", clean_actor)
        object.__setattr__(self, "correlation_id", clean_correlation_id)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Tenant-scoped reservation tying an idempotency key to a single job."""

    tenant_id: TenantId
    idempotency_key: IdempotencyKey
    request_id: RequestId
    job_id: JobId
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        _require_aware_datetime("created_at", self.created_at)
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match idempotency tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match idempotency tenant")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Immutable audit event for job lifecycle and idempotency operations."""

    event_id: str
    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    event_type: str
    recorded_at: datetime = field(default_factory=_utc_now)
    audit_metadata: AuditMetadata = field(default_factory=AuditMetadata)
    from_status: ExecutionStatus | None = None
    to_status: ExecutionStatus | None = None
    summary: ResultSummary | None = None
    error: ErrorDetails | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_event_id = self.event_id.strip()
        if not clean_event_id:
            raise ValueError("audit event id must not be empty")
        clean_event_type = self.event_type.strip()
        if not clean_event_type:
            raise ValueError("audit event type must not be empty")
        _require_aware_datetime("recorded_at", self.recorded_at)
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match audit event tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match audit event tenant")
        object.__setattr__(self, "event_id", clean_event_id)
        object.__setattr__(self, "event_type", clean_event_type)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class JobRecord(Generic[RequestPayloadT, ResultPayloadT]):
    """Stable persisted view of a tenant-scoped job and its latest outcome."""

    tenant_id: TenantId
    request: ExecutionRequest[RequestPayloadT]
    state: ExecutionState
    result: ExecutionResult[ResultPayloadT] | None = None

    def __post_init__(self) -> None:
        if self.request.tenant_id != self.tenant_id:
            raise ValueError("request tenant must match job record tenant")
        if self.state.tenant_id != self.tenant_id:
            raise ValueError("state tenant must match job record tenant")
        if self.request.request_id != self.state.request_id:
            raise ValueError("request id must match state request id")
        if self.request.job_id != self.state.job_id:
            raise ValueError("job id must match state job id")
        if self.result is not None:
            if self.result.tenant_id != self.tenant_id:
                raise ValueError("result tenant must match job record tenant")
            if self.result.request_id != self.request.request_id:
                raise ValueError("result request id must match job record request id")
            if self.result.job_id != self.request.job_id:
                raise ValueError("result job id must match job record job id")
            if self.result.status != self.state.status:
                raise ValueError("result status must match job record state status")
            if self.state.finished_at != self.result.completed_at:
                raise ValueError(
                    "result completion time must match job record finished_at"
                )


@dataclass(frozen=True, slots=True)
class ArtifactContentRef:
    """Opaque reference to artifact bytes managed by a content store."""

    storage_backend: str
    locator: str

    def __post_init__(self) -> None:
        clean_backend = self.storage_backend.strip()
        clean_locator = self.locator.strip()
        if not clean_backend:
            raise ValueError("artifact content backend must not be empty")
        if not clean_locator:
            raise ValueError("artifact content locator must not be empty")
        object.__setattr__(self, "storage_backend", clean_backend)
        object.__setattr__(self, "locator", clean_locator)


@dataclass(frozen=True, slots=True)
class ArtifactMetadataRecord:
    """Tenant-scoped persisted artifact metadata without the underlying bytes."""

    tenant_id: TenantId
    job_id: JobId
    artifact: ArtifactSummary
    created_at: datetime = field(default_factory=_utc_now)
    content_ref: ArtifactContentRef | None = None

    def __post_init__(self) -> None:
        _require_aware_datetime("created_at", self.created_at)
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match artifact tenant")

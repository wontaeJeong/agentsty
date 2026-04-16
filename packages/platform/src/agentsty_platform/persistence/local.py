"""Baseline local persistence implementations for development and tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Generic, TypeVar

from ..domain.errors import ErrorCategory, ErrorDetails
from ..domain.execution import (
    CancellationState,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    TimeoutState,
)
from ..domain.ids import IdempotencyKey, JobId, RequestId, TenantId
from ..domain.models import ArtifactSummary, ResultSummary
from .models import (
    ArtifactContentRef,
    ArtifactMetadataRecord,
    AuditEvent,
    AuditMetadata,
    IdempotencyRecord,
    JobRecord,
)

RequestPayloadT = TypeVar("RequestPayloadT")
ResultPayloadT = TypeVar("ResultPayloadT")


def _tenant_key(tenant_id: TenantId) -> str:
    return tenant_id.value


def _job_key(tenant_id: TenantId, job_id: JobId) -> tuple[str, str]:
    _require_tenant_match("job id", tenant_id, job_id.tenant_id)
    return (_tenant_key(tenant_id), job_id.value)


def _request_key(tenant_id: TenantId, request_id: RequestId) -> tuple[str, str]:
    _require_tenant_match("request id", tenant_id, request_id.tenant_id)
    return (_tenant_key(tenant_id), request_id.value)


def _idempotency_key(
    tenant_id: TenantId, idempotency_key: IdempotencyKey
) -> tuple[str, str]:
    return (_tenant_key(tenant_id), idempotency_key.value)


def _require_tenant_match(
    name: str, tenant_id: TenantId, scoped_tenant: TenantId
) -> None:
    if tenant_id != scoped_tenant:
        raise ValueError(f"{name} tenant must match lookup tenant")


def _coerce_audit_metadata(audit_metadata: AuditMetadata | None) -> AuditMetadata:
    return AuditMetadata() if audit_metadata is None else audit_metadata


def _terminal_error_category(status: ExecutionStatus) -> ErrorCategory | None:
    if status is ExecutionStatus.TIMED_OUT:
        return ErrorCategory.TIMEOUT
    if status is ExecutionStatus.CANCELLED:
        return ErrorCategory.CANCELLATION
    return None


def _sanitize_artifact_key(artifact_key: str) -> PurePosixPath:
    candidate = PurePosixPath(artifact_key.strip())
    if artifact_key.strip() == "":
        raise ValueError("artifact key must not be empty")
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError("artifact key must be a safe relative path")
    return candidate


@dataclass(slots=True)
class InMemoryJobRepository(Generic[RequestPayloadT, ResultPayloadT]):
    """Tenant-isolated in-memory job repository with audit and idempotency support."""

    _jobs: dict[tuple[str, str], JobRecord[RequestPayloadT, ResultPayloadT]] = field(
        default_factory=dict
    )
    _request_index: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    _idempotency_index: dict[tuple[str, str], IdempotencyRecord] = field(
        default_factory=dict
    )
    _audit_events: dict[tuple[str, str], list[AuditEvent]] = field(default_factory=dict)
    _audit_sequence: int = 0

    def create(
        self, request: ExecutionRequest[RequestPayloadT]
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        execution_request = request
        tenant_id = execution_request.tenant_id
        job_key = _job_key(tenant_id, execution_request.job_id)
        request_key = _request_key(tenant_id, execution_request.request_id)
        if job_key in self._jobs:
            raise ValueError("job already exists for tenant")
        if request_key in self._request_index:
            raise ValueError("request already exists for tenant")
        state = ExecutionState(
            tenant_id=tenant_id,
            request_id=execution_request.request_id,
            job_id=execution_request.job_id,
            status=ExecutionStatus.RECEIVED,
            submitted_at=execution_request.submitted_at,
            updated_at=execution_request.submitted_at,
        )
        record: JobRecord[RequestPayloadT, ResultPayloadT] = JobRecord(
            tenant_id=tenant_id,
            request=execution_request,
            state=state,
        )
        self._jobs[job_key] = record
        self._request_index[request_key] = job_key
        _ = self._append_audit_event(
            tenant_id=tenant_id,
            request_id=execution_request.request_id,
            job_id=execution_request.job_id,
            event_type="job_created",
            to_status=ExecutionStatus.RECEIVED,
            recorded_at=execution_request.submitted_at,
        )
        return record

    def get(
        self, tenant_id: TenantId, job_id: JobId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        try:
            return self._jobs[_job_key(tenant_id, job_id)]
        except KeyError as exc:
            raise KeyError(f"job not found for tenant: {job_id.value}") from exc

    def get_by_request_id(
        self, tenant_id: TenantId, request_id: RequestId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        request_key = _request_key(tenant_id, request_id)
        try:
            job_key = self._request_index[request_key]
        except KeyError as exc:
            raise KeyError(f"request not found for tenant: {request_id.value}") from exc
        return self._jobs[job_key]

    def find_by_idempotency_key(
        self, tenant_id: TenantId, idempotency_key: IdempotencyKey
    ) -> IdempotencyRecord | None:
        return self._idempotency_index.get(_idempotency_key(tenant_id, idempotency_key))

    def reserve_idempotency(
        self,
        tenant_id: TenantId,
        idempotency_key: IdempotencyKey,
        request_id: RequestId,
        job_id: JobId,
        *,
        created_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> IdempotencyRecord:
        _require_tenant_match("request id", tenant_id, request_id.tenant_id)
        _require_tenant_match("job id", tenant_id, job_id.tenant_id)
        key = _idempotency_key(tenant_id, idempotency_key)
        existing = self._idempotency_index.get(key)
        if existing is not None:
            if existing.request_id != request_id or existing.job_id != job_id:
                raise ValueError(
                    "idempotency key is already reserved for a different job"
                )
            return existing
        record = IdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            job_id=job_id,
            created_at=(created_at or datetime.now(UTC)),
        )
        self._idempotency_index[key] = record
        _ = self._append_audit_event(
            tenant_id=tenant_id,
            request_id=request_id,
            job_id=job_id,
            event_type="idempotency_reserved",
            recorded_at=record.created_at,
            audit_metadata=_coerce_audit_metadata(audit_metadata),
            metadata=(("idempotency_key", idempotency_key.value),),
        )
        return record

    def mark_validated(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.VALIDATED,
            updated_at=updated_at,
            audit_metadata=audit_metadata,
        )

    def mark_queued(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.QUEUED,
            updated_at=updated_at,
            audit_metadata=audit_metadata,
        )

    def mark_starting(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        started_at: datetime,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.STARTING,
            started_at=started_at,
            updated_at=(updated_at or started_at),
            audit_metadata=audit_metadata,
        )

    def mark_running(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.RUNNING,
            updated_at=updated_at,
            timeout_state=TimeoutState.ACTIVE,
            audit_metadata=audit_metadata,
        )

    def request_cancellation(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.CANCELLING,
            updated_at=updated_at,
            cancellation_state=CancellationState.REQUESTED,
            audit_metadata=audit_metadata,
        )

    def mark_succeeded(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        payload: ResultPayloadT | None = None,
        summary: ResultSummary | None = None,
        artifacts: tuple[ArtifactSummary, ...] = (),
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.SUCCEEDED,
            finished_at=finished_at,
            payload=payload,
            summary=summary,
            artifacts=artifacts,
            timeout_state=TimeoutState.CLEARED,
            audit_metadata=audit_metadata,
        )

    def mark_failed(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.FAILED,
            finished_at=finished_at,
            error=error,
            summary=summary,
            audit_metadata=audit_metadata,
        )

    def mark_timed_out(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.TIMED_OUT,
            finished_at=finished_at,
            error=error,
            summary=summary,
            timeout_state=TimeoutState.EXCEEDED,
            audit_metadata=audit_metadata,
        )

    def mark_cancelled(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.CANCELLED,
            finished_at=finished_at,
            error=error,
            summary=summary,
            cancellation_state=CancellationState.COMPLETED,
            audit_metadata=audit_metadata,
        )

    def list_audit_events(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[AuditEvent, ...]:
        return tuple(self._audit_events.get(_job_key(tenant_id, job_id), ()))

    def _transition_non_terminal(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        status: ExecutionStatus,
        updated_at: datetime | None,
        started_at: datetime | None = None,
        cancellation_state: CancellationState | None = None,
        timeout_state: TimeoutState | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        record = self.get(tenant_id, job_id)
        previous_state = record.state
        next_state = record.state.transition_to(
            status,
            updated_at=updated_at,
            started_at=started_at,
            cancellation_state=cancellation_state,
            timeout_state=timeout_state,
        )
        updated_record = replace(record, state=next_state, result=None)
        self._store_record(updated_record)
        _ = self._append_audit_event(
            tenant_id=tenant_id,
            request_id=record.request.request_id,
            job_id=job_id,
            event_type="job_status_changed",
            recorded_at=next_state.updated_at,
            audit_metadata=_coerce_audit_metadata(audit_metadata),
            from_status=previous_state.status,
            to_status=next_state.status,
            summary=next_state.summary,
            error=next_state.error,
        )
        return updated_record

    def _transition_terminal(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        status: ExecutionStatus,
        finished_at: datetime,
        payload: ResultPayloadT | None = None,
        summary: ResultSummary | None = None,
        artifacts: tuple[ArtifactSummary, ...] = (),
        error: ErrorDetails | None = None,
        cancellation_state: CancellationState | None = None,
        timeout_state: TimeoutState | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        required_category = _terminal_error_category(status)
        if status is ExecutionStatus.SUCCEEDED and error is not None:
            raise ValueError("successful executions must not include an error")
        if status is not ExecutionStatus.SUCCEEDED and error is None:
            raise ValueError(f"{status.value} executions must include an error")
        if required_category is not None:
            assert error is not None
            if error.category is not required_category and status in {
                ExecutionStatus.TIMED_OUT,
                ExecutionStatus.CANCELLED,
            }:
                raise ValueError(
                    f"{status.value} executions must use matching error details"
                )
        record = self.get(tenant_id, job_id)
        previous_state = record.state
        next_state = record.state.transition_to(
            status,
            updated_at=finished_at,
            finished_at=finished_at,
            cancellation_state=cancellation_state,
            timeout_state=timeout_state,
            summary=summary,
            error=error,
        )
        result = ExecutionResult(
            tenant_id=record.tenant_id,
            request_id=record.request.request_id,
            job_id=record.request.job_id,
            status=status,
            completed_at=finished_at,
            payload=payload,
            summary=summary,
            artifacts=artifacts,
            error=error,
        )
        updated_record = replace(record, state=next_state, result=result)
        self._store_record(updated_record)
        _ = self._append_audit_event(
            tenant_id=tenant_id,
            request_id=record.request.request_id,
            job_id=job_id,
            event_type="job_status_changed",
            recorded_at=finished_at,
            audit_metadata=_coerce_audit_metadata(audit_metadata),
            from_status=previous_state.status,
            to_status=next_state.status,
            summary=summary,
            error=error,
            metadata=(("terminal", "true"),),
        )
        return updated_record

    def _store_record(self, record: JobRecord[RequestPayloadT, ResultPayloadT]) -> None:
        self._jobs[_job_key(record.tenant_id, record.request.job_id)] = record

    def _append_audit_event(
        self,
        *,
        tenant_id: TenantId,
        request_id: RequestId,
        job_id: JobId,
        event_type: str,
        recorded_at: datetime,
        audit_metadata: AuditMetadata | None = None,
        from_status: ExecutionStatus | None = None,
        to_status: ExecutionStatus | None = None,
        summary: ResultSummary | None = None,
        error: ErrorDetails | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> AuditEvent:
        self._audit_sequence += 1
        event = AuditEvent(
            event_id=f"audit-{self._audit_sequence:06d}",
            tenant_id=tenant_id,
            request_id=request_id,
            job_id=job_id,
            event_type=event_type,
            recorded_at=recorded_at,
            audit_metadata=_coerce_audit_metadata(audit_metadata),
            from_status=from_status,
            to_status=to_status,
            summary=summary,
            error=error,
            metadata=metadata,
        )
        self._audit_events.setdefault(_job_key(tenant_id, job_id), []).append(event)
        return event


@dataclass(slots=True)
class InMemoryArtifactMetadataRepository:
    """Tenant-scoped in-memory artifact metadata repository."""

    _records: dict[tuple[str, str, str], ArtifactMetadataRecord] = field(
        default_factory=dict
    )

    def put(self, record: ArtifactMetadataRecord) -> ArtifactMetadataRecord:
        key = (_tenant_key(record.tenant_id), record.job_id.value, record.artifact.key)
        self._records[key] = record
        return record

    def get(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str
    ) -> ArtifactMetadataRecord | None:
        _require_tenant_match("job id", tenant_id, job_id.tenant_id)
        return self._records.get(
            (_tenant_key(tenant_id), job_id.value, artifact_key.strip())
        )

    def list_for_job(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[ArtifactMetadataRecord, ...]:
        _require_tenant_match("job id", tenant_id, job_id.tenant_id)
        prefix = (_tenant_key(tenant_id), job_id.value)
        records = [record for key, record in self._records.items() if key[:2] == prefix]
        records.sort(key=lambda record: (record.created_at, record.artifact.key))
        return tuple(records)


@dataclass(slots=True)
class LocalFileArtifactContentStore:
    """Local filesystem artifact content store with safe relative paths."""

    root: Path

    def __post_init__(self) -> None:
        return None

    def write(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str, content: bytes
    ) -> ArtifactContentRef:
        relative_path = self._relative_path(tenant_id, job_id, artifact_key)
        absolute_path = self.root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        _ = absolute_path.write_bytes(content)
        return ArtifactContentRef(
            storage_backend="local_fs", locator=relative_path.as_posix()
        )

    def read(self, tenant_id: TenantId, job_id: JobId, artifact_key: str) -> bytes:
        absolute_path = self.root / self._relative_path(tenant_id, job_id, artifact_key)
        if not absolute_path.exists():
            raise KeyError(f"artifact content not found: {artifact_key}")
        return absolute_path.read_bytes()

    def _relative_path(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str
    ) -> PurePosixPath:
        _require_tenant_match("job id", tenant_id, job_id.tenant_id)
        artifact_path = _sanitize_artifact_key(artifact_key)
        return PurePosixPath(tenant_id.value, job_id.value, *artifact_path.parts)


@dataclass(slots=True)
class LocalPersistence:
    """Convenience bundle exposing the baseline local persistence primitives."""

    jobs: InMemoryJobRepository[object, object]
    artifact_metadata: InMemoryArtifactMetadataRepository
    artifact_content: LocalFileArtifactContentStore

    @classmethod
    def create(cls, artifact_root: Path) -> LocalPersistence:
        return cls(
            jobs=InMemoryJobRepository(),
            artifact_metadata=InMemoryArtifactMetadataRepository(),
            artifact_content=LocalFileArtifactContentStore(artifact_root),
        )

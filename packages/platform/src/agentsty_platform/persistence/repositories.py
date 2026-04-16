"""Persistence contracts for jobs, audits, and artifact storage."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, TypeVar

from ..domain.errors import ErrorDetails
from ..domain.execution import ExecutionRequest
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


class JobRepository(Protocol[RequestPayloadT, ResultPayloadT]):
    """Contract for tenant-isolated job persistence with explicit lifecycle steps."""

    def create(
        self, request: ExecutionRequest[RequestPayloadT]
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def get(
        self, tenant_id: TenantId, job_id: JobId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def get_by_request_id(
        self, tenant_id: TenantId, request_id: RequestId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def find_by_idempotency_key(
        self, tenant_id: TenantId, idempotency_key: IdempotencyKey
    ) -> IdempotencyRecord | None: ...

    def reserve_idempotency(
        self,
        tenant_id: TenantId,
        idempotency_key: IdempotencyKey,
        request_id: RequestId,
        job_id: JobId,
        *,
        created_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> IdempotencyRecord: ...

    def mark_validated(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_queued(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_starting(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        started_at: datetime,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_running(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def request_cancellation(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

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
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_failed(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_timed_out(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def mark_cancelled(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]: ...

    def list_audit_events(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[AuditEvent, ...]: ...


class ArtifactMetadataRepository(Protocol):
    """Contract for tenant-scoped artifact metadata independent of bytes storage."""

    def put(self, record: ArtifactMetadataRecord) -> ArtifactMetadataRecord: ...

    def get(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str
    ) -> ArtifactMetadataRecord | None: ...

    def list_for_job(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[ArtifactMetadataRecord, ...]: ...


class ArtifactContentStore(Protocol):
    """Contract for artifact bytes kept separate from artifact metadata."""

    def write(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str, content: bytes
    ) -> ArtifactContentRef: ...

    def read(self, tenant_id: TenantId, job_id: JobId, artifact_key: str) -> bytes: ...

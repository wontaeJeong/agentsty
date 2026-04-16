"""Execution lifecycle contracts shared across orchestration boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, TypeVar

from .errors import ErrorCategory, ErrorDetails
from .ids import IdempotencyKey, JobId, RequestId, TenantId
from .models import (
    ArtifactSummary,
    ExecutionTimeouts,
    Metadata,
    ResultSummary,
    normalize_metadata,
)

RequestPayloadT = TypeVar("RequestPayloadT")
ResultPayloadT = TypeVar("ResultPayloadT")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class ExecutionStatus(StrEnum):
    """Stable execution lifecycle progression independent of any executor."""

    RECEIVED = "received"
    VALIDATED = "validated"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.TIMED_OUT,
            self.CANCELLED,
        }

    def can_transition_to(self, target: ExecutionStatus) -> bool:
        return target in _ALLOWED_STATUS_TRANSITIONS[self]


class CancellationState(StrEnum):
    """Cancellation lifecycle independent of executor implementation details."""

    OPEN = "open"
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"


class TimeoutState(StrEnum):
    """Timeout tracking state for an execution."""

    PENDING = "pending"
    ACTIVE = "active"
    EXCEEDED = "exceeded"
    CLEARED = "cleared"


_ALLOWED_STATUS_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.RECEIVED: frozenset(
        {ExecutionStatus.VALIDATED, ExecutionStatus.CANCELLED}
    ),
    ExecutionStatus.VALIDATED: frozenset(
        {ExecutionStatus.QUEUED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
    ),
    ExecutionStatus.QUEUED: frozenset(
        {
            ExecutionStatus.STARTING,
            ExecutionStatus.CANCELLING,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
        }
    ),
    ExecutionStatus.STARTING: frozenset(
        {
            ExecutionStatus.RUNNING,
            ExecutionStatus.CANCELLING,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
        }
    ),
    ExecutionStatus.RUNNING: frozenset(
        {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLING,
            ExecutionStatus.CANCELLED,
        }
    ),
    ExecutionStatus.CANCELLING: frozenset(
        {ExecutionStatus.CANCELLED, ExecutionStatus.FAILED}
    ),
    ExecutionStatus.SUCCEEDED: frozenset(),
    ExecutionStatus.FAILED: frozenset(),
    ExecutionStatus.TIMED_OUT: frozenset(),
    ExecutionStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ExecutionRequest(Generic[RequestPayloadT]):
    """Executor-neutral request contract for a single tenant-scoped execution."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    idempotency_key: IdempotencyKey
    payload: RequestPayloadT
    submitted_at: datetime = field(default_factory=_utc_now)
    timeouts: ExecutionTimeouts = field(default_factory=ExecutionTimeouts)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_aware_datetime("submitted_at", self.submitted_at)
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match execution tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match execution tenant")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ExecutionState:
    """Current execution lifecycle state and control-plane metadata."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    status: ExecutionStatus = ExecutionStatus.RECEIVED
    submitted_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellation_state: CancellationState = CancellationState.OPEN
    timeout_state: TimeoutState = TimeoutState.PENDING
    summary: ResultSummary | None = None
    error: ErrorDetails | None = None

    def __post_init__(self) -> None:
        _require_aware_datetime("submitted_at", self.submitted_at)
        _require_aware_datetime("updated_at", self.updated_at)
        if self.updated_at < self.submitted_at:
            raise ValueError("updated_at must not be earlier than submitted_at")
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match execution tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match execution tenant")
        if self.started_at is not None:
            _require_aware_datetime("started_at", self.started_at)
            if self.started_at < self.submitted_at:
                raise ValueError("started_at must not be earlier than submitted_at")
        if self.finished_at is not None:
            _require_aware_datetime("finished_at", self.finished_at)
            if self.finished_at < self.submitted_at:
                raise ValueError("finished_at must not be earlier than submitted_at")
            if self.started_at is not None and self.finished_at < self.started_at:
                raise ValueError("finished_at must not be earlier than started_at")
        if self.status.is_terminal and self.finished_at is None:
            raise ValueError("terminal execution states must include finished_at")
        if not self.status.is_terminal and self.finished_at is not None:
            raise ValueError(
                "non-terminal execution states must not include finished_at"
            )
        if (
            self.status
            in {
                ExecutionStatus.RUNNING,
                ExecutionStatus.CANCELLING,
                ExecutionStatus.SUCCEEDED,
                ExecutionStatus.TIMED_OUT,
            }
            and self.started_at is None
        ):
            raise ValueError(f"{self.status.value} state must include started_at")
        if self.status == ExecutionStatus.SUCCEEDED and self.error is not None:
            raise ValueError("successful executions must not include an error")
        if (
            self.status
            in {
                ExecutionStatus.FAILED,
                ExecutionStatus.TIMED_OUT,
                ExecutionStatus.CANCELLED,
            }
            and self.error is None
        ):
            raise ValueError(f"{self.status.value} state must include an error")
        if (
            self.status == ExecutionStatus.TIMED_OUT
            and self.timeout_state != TimeoutState.EXCEEDED
        ):
            raise ValueError("timed out executions must mark timeout_state as exceeded")
        if (
            self.status == ExecutionStatus.TIMED_OUT
            and self.error is not None
            and self.error.category != ErrorCategory.TIMEOUT
        ):
            raise ValueError("timed out executions must use timeout error details")
        if (
            self.status == ExecutionStatus.CANCELLED
            and self.cancellation_state != CancellationState.COMPLETED
        ):
            raise ValueError(
                "cancelled executions must mark cancellation_state as completed"
            )
        if (
            self.status == ExecutionStatus.CANCELLED
            and self.error is not None
            and self.error.category != ErrorCategory.CANCELLATION
        ):
            raise ValueError("cancelled executions must use cancellation error details")

    def transition_to(
        self,
        status: ExecutionStatus,
        *,
        updated_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        cancellation_state: CancellationState | None = None,
        timeout_state: TimeoutState | None = None,
        summary: ResultSummary | None = None,
        error: ErrorDetails | None = None,
    ) -> ExecutionState:
        if not self.status.can_transition_to(status):
            raise ValueError(
                f"cannot transition execution from {self.status.value} to {status.value}"
            )
        effective_updated_at = updated_at or _utc_now()
        return replace(
            self,
            status=status,
            updated_at=effective_updated_at,
            started_at=started_at if started_at is not None else self.started_at,
            finished_at=finished_at,
            cancellation_state=(
                cancellation_state
                if cancellation_state is not None
                else self.cancellation_state
            ),
            timeout_state=timeout_state
            if timeout_state is not None
            else self.timeout_state,
            summary=summary if summary is not None else self.summary,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult(Generic[ResultPayloadT]):
    """Terminal outcome contract for a completed execution."""

    tenant_id: TenantId
    request_id: RequestId
    job_id: JobId
    status: ExecutionStatus
    completed_at: datetime
    payload: ResultPayloadT | None = None
    summary: ResultSummary | None = None
    artifacts: tuple[ArtifactSummary, ...] = field(default_factory=tuple)
    error: ErrorDetails | None = None

    def __post_init__(self) -> None:
        _require_aware_datetime("completed_at", self.completed_at)
        if self.request_id.tenant_id != self.tenant_id:
            raise ValueError("request id tenant must match execution tenant")
        if self.job_id.tenant_id != self.tenant_id:
            raise ValueError("job id tenant must match execution tenant")
        if not self.status.is_terminal:
            raise ValueError("execution result status must be terminal")
        if self.status == ExecutionStatus.SUCCEEDED:
            if self.error is not None:
                raise ValueError("successful results must not include an error")
        else:
            if self.error is None:
                raise ValueError("non-successful results must include an error")
        if (
            self.status == ExecutionStatus.TIMED_OUT
            and self.error is not None
            and self.error.category != ErrorCategory.TIMEOUT
        ):
            raise ValueError("timed out results must use timeout error details")
        if (
            self.status == ExecutionStatus.CANCELLED
            and self.error is not None
            and self.error.category != ErrorCategory.CANCELLATION
        ):
            raise ValueError("cancelled results must use cancellation error details")

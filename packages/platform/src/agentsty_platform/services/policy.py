"""Policy and quota evaluation services for orchestration intake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..domain.errors import ErrorDetails, PolicyViolationError, QuotaExceededError
from ..domain.ids import JobId, TenantId
from ..domain.models import Metadata, normalize_metadata
from ..observability.tracing import TraceContext
from .models import ExecutionSubmitRequest


@dataclass(frozen=True, slots=True)
class PolicyQuotaDecision:
    """Stable policy or quota outcome for one orchestration step."""

    allowed: bool
    metadata: Metadata = field(default_factory=tuple)
    error: ErrorDetails | None = None

    def __post_init__(self) -> None:
        if not self.allowed and self.error is None:
            raise ValueError("rejected policy decisions must include an error")
        if self.allowed and self.error is not None:
            raise ValueError("allowed policy decisions must not include an error")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    def require_allowed(self) -> None:
        if self.allowed:
            return
        assert self.error is not None
        if self.error.category.value == "quota_exceeded":
            raise QuotaExceededError(
                self.error.message,
                code=self.error.code,
                retryable=self.error.retryable,
                metadata=self.error.metadata,
            )
        raise PolicyViolationError(
            self.error.message,
            code=self.error.code,
            retryable=self.error.retryable,
            metadata=self.error.metadata,
        )


class PolicyQuotaService(Protocol):
    """Contract for pluggable policy/quota enforcement."""

    def evaluate_submission(
        self,
        request: ExecutionSubmitRequest,
        *,
        trace_context: TraceContext | None = None,
    ) -> PolicyQuotaDecision: ...

    def acquire_execution_slot(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        trace_context: TraceContext | None = None,
    ) -> PolicyQuotaDecision: ...

    def release_execution_slot(self, tenant_id: TenantId, job_id: JobId) -> None: ...


@dataclass(slots=True)
class InMemoryPolicyQuotaService:
    """Practical baseline policy/quota implementation for local orchestration."""

    max_active_executions_per_tenant: int = 1
    max_messages_per_request: int = 32
    denied_tenants: frozenset[str] = field(default_factory=frozenset)
    blocked_models: frozenset[str] = field(default_factory=frozenset)
    _active_jobs_by_tenant: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_active_executions_per_tenant < 1:
            raise ValueError("max_active_executions_per_tenant must be at least 1")
        if self.max_messages_per_request < 1:
            raise ValueError("max_messages_per_request must be at least 1")

    def evaluate_submission(
        self,
        request: ExecutionSubmitRequest,
        *,
        trace_context: TraceContext | None = None,
    ) -> PolicyQuotaDecision:
        del trace_context
        tenant_value = request.tenant_id.value
        if tenant_value in self.denied_tenants:
            return PolicyQuotaDecision(
                allowed=False,
                error=PolicyViolationError(
                    "tenant is not allowed to submit executions",
                    metadata=(("tenant_id", tenant_value),),
                ).as_details(),
            )
        if len(request.gateway_request.messages) > self.max_messages_per_request:
            return PolicyQuotaDecision(
                allowed=False,
                error=PolicyViolationError(
                    "request exceeds the maximum allowed message count",
                    metadata=(
                        ("message_count", str(len(request.gateway_request.messages))),
                        ("max_messages", str(self.max_messages_per_request)),
                    ),
                ).as_details(),
            )
        if request.gateway_request.target.label in self.blocked_models:
            return PolicyQuotaDecision(
                allowed=False,
                error=PolicyViolationError(
                    "requested model target is blocked by policy",
                    metadata=(("target", request.gateway_request.target.label),),
                ).as_details(),
            )
        return PolicyQuotaDecision(
            allowed=True,
            metadata=(("tenant_id", tenant_value),),
        )

    def acquire_execution_slot(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        trace_context: TraceContext | None = None,
    ) -> PolicyQuotaDecision:
        del trace_context
        tenant_jobs = self._active_jobs_by_tenant.setdefault(tenant_id.value, set())
        if job_id.value in tenant_jobs:
            return PolicyQuotaDecision(
                allowed=True,
                metadata=(("tenant_id", tenant_id.value), ("reused", "true")),
            )
        if len(tenant_jobs) >= self.max_active_executions_per_tenant:
            return PolicyQuotaDecision(
                allowed=False,
                error=QuotaExceededError(
                    "tenant has no remaining execution quota",
                    retryable=True,
                    metadata=(
                        ("tenant_id", tenant_id.value),
                        (
                            "max_active_executions_per_tenant",
                            str(self.max_active_executions_per_tenant),
                        ),
                    ),
                ).as_details(),
            )
        tenant_jobs.add(job_id.value)
        return PolicyQuotaDecision(
            allowed=True,
            metadata=(
                ("tenant_id", tenant_id.value),
                ("active_jobs", str(len(tenant_jobs))),
            ),
        )

    def release_execution_slot(self, tenant_id: TenantId, job_id: JobId) -> None:
        tenant_jobs = self._active_jobs_by_tenant.get(tenant_id.value)
        if tenant_jobs is None:
            return
        tenant_jobs.discard(job_id.value)
        if not tenant_jobs:
            del self._active_jobs_by_tenant[tenant_id.value]

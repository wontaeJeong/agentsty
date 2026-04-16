"""Request intake service for tenant-scoped idempotent orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from ..domain.execution import ExecutionRequest
from ..domain.ids import JobId, RequestId
from ..gateway.contracts import GatewayRequest, GatewayResponse
from ..observability.tracing import TraceContext
from ..persistence.models import JobRecord
from ..persistence.repositories import JobRepository
from .models import ExecutionSubmitRequest


def _new_request_id(request: ExecutionSubmitRequest) -> RequestId:
    return RequestId(tenant_id=request.tenant_id, value=f"req-{uuid4().hex}")


def _new_job_id(request: ExecutionSubmitRequest) -> JobId:
    return JobId(tenant_id=request.tenant_id, value=f"job-{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class RequestIntakeResult:
    """Result of request intake before execution lifecycle orchestration."""

    job: JobRecord[GatewayRequest, GatewayResponse]
    execution: ExecutionRequest[GatewayRequest]
    trace_context: TraceContext
    idempotent_replay: bool = False


@dataclass(slots=True)
class RequestIntakeService:
    """Service that creates tenant-scoped requests with idempotency protection."""

    jobs: JobRepository[GatewayRequest, GatewayResponse]
    request_id_factory: Callable[[ExecutionSubmitRequest], RequestId] = _new_request_id
    job_id_factory: Callable[[ExecutionSubmitRequest], JobId] = _new_job_id

    def intake(self, request: ExecutionSubmitRequest) -> RequestIntakeResult:
        existing = self.jobs.find_by_idempotency_key(
            request.tenant_id,
            request.idempotency_key,
        )
        if existing is not None:
            record = self.jobs.get(request.tenant_id, existing.job_id)
            trace_context = request.trace_context or TraceContext.new(
                tenant_id=request.tenant_id,
                request_id=record.request.request_id,
                job_id=record.request.job_id,
                metadata=(("idempotent_replay", "true"),),
            )
            return RequestIntakeResult(
                job=record,
                execution=record.request,
                trace_context=trace_context,
                idempotent_replay=True,
            )

        request_id = request.request_id or self.request_id_factory(request)
        job_id = request.job_id or self.job_id_factory(request)
        trace_context = (
            request.trace_context.bind(
                tenant_id=request.tenant_id,
                request_id=request_id,
                job_id=job_id,
                metadata=(("service", "request_intake"),),
            )
            if request.trace_context is not None
            else TraceContext.new(
                tenant_id=request.tenant_id,
                request_id=request_id,
                job_id=job_id,
                metadata=(("service", "request_intake"),),
            )
        )
        execution = ExecutionRequest(
            tenant_id=request.tenant_id,
            request_id=request_id,
            job_id=job_id,
            idempotency_key=request.idempotency_key,
            payload=request.gateway_request,
            timeouts=request.timeouts,
            metadata=request.metadata + trace_context.to_metadata(),
        )
        self.jobs.reserve_idempotency(
            request.tenant_id,
            request.idempotency_key,
            request_id,
            job_id,
            created_at=execution.submitted_at,
            audit_metadata=request.audit_metadata,
        )
        record = self.jobs.create(execution)
        return RequestIntakeResult(
            job=record,
            execution=execution,
            trace_context=trace_context,
        )

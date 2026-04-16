"""FastAPI route handlers that adapt HTTP requests onto shared services."""

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any, Protocol, cast

from fastapi import APIRouter, Depends, Header, Request, Response, status

from .auth import (
    EffectiveRequestIdentity,
    resolve_job_identity,
    resolve_submission_identity,
)
from .dependencies import APIDependencies
from .errors import map_error_details
from .schemas import (
    ArtifactContentRefResponse,
    ArtifactResponse,
    CancellationResponse,
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ErrorResponseBody,
    ExecutionSummaryResponse,
    HealthComponentResponse,
    HealthResponse,
    ReadinessCheckResponse,
    ReadinessResponse,
    UsageResponse,
)


class RequestStateLike(Protocol):
    status: object
    submitted_at: datetime
    summary: SummaryLike | None


class ScopedIdLike(Protocol):
    value: str


class GatewayTargetLike(Protocol):
    model: str


class GatewayRequestPayloadLike(Protocol):
    target: GatewayTargetLike


class GatewayMessageLike(Protocol):
    role: object
    content: str
    name: str | None


class GatewayUsageLike(Protocol):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class GatewayResultPayloadLike(Protocol):
    message: GatewayMessageLike
    finish_reason: object
    usage: GatewayUsageLike


class ErrorDetailsLike(Protocol):
    message: str
    category: object
    code: str | None
    retryable: bool
    metadata: tuple[tuple[str, str], ...]


class SummaryLike(Protocol):
    output_text: str | None
    duration_seconds: float | None
    artifact_count: int
    metadata: tuple[tuple[str, str], ...]


class ArtifactContentRefLike(Protocol):
    storage_backend: str
    locator: str


class ArtifactLike(Protocol):
    artifact: object
    content_ref: ArtifactContentRefLike | None


class ArtifactSummaryLike(Protocol):
    key: str
    media_type: str | None
    size_bytes: int
    sha256: str | None
    redacted: bool
    metadata: tuple[tuple[str, str], ...]


class ResultLike(Protocol):
    payload: GatewayResultPayloadLike | None
    error: ErrorDetailsLike | None


class RequestPayloadLike(Protocol):
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    submitted_at: datetime
    payload: GatewayRequestPayloadLike


class JobRecordLike(Protocol):
    tenant_id: ScopedIdLike
    request: RequestPayloadLike
    state: RequestStateLike
    result: ResultLike | None


class SubmitResultLike(Protocol):
    job: JobRecordLike
    idempotent_replay: bool
    cleanup_performed: bool


class PollResultLike(Protocol):
    job: JobRecordLike
    cleanup_performed: bool


class CancellationResultLike(Protocol):
    job: JobRecordLike
    cancellation_requested: bool
    cleanup_performed: bool


class HealthComponentLike(Protocol):
    name: str
    status: object
    detail: str | None
    metadata: tuple[tuple[str, str], ...]


class HealthReportLike(Protocol):
    service_name: str
    status: object
    checked_at: datetime
    summary: str | None
    components: tuple[HealthComponentLike, ...]


class ReadinessCheckLike(Protocol):
    name: str
    ready: bool
    requirement: object
    detail: str | None
    metadata: tuple[tuple[str, str], ...]


class ReadinessReportLike(Protocol):
    service_name: str
    ready: bool
    checked_at: datetime
    summary: str | None
    blocking_checks: tuple[str, ...]
    checks: tuple[ReadinessCheckLike, ...]


def _domain_module() -> Any:
    return import_module("agentsty_platform.domain")


def _gateway_module() -> Any:
    return import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return import_module("agentsty_platform.observability")


def _services_module() -> Any:
    return import_module("agentsty_platform.services")


def get_api_dependencies(request: Request) -> APIDependencies:
    """Resolve the API dependency bundle from application state."""

    return cast(APIDependencies, request.app.state.agentsty_dependencies)


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(
    response: Response,
    dependencies: APIDependencies = Depends(get_api_dependencies),
) -> HealthResponse:
    report = cast(HealthReportLike, dependencies.health_reporter.build_report())
    if str(report.status) == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service_name=report.service_name,
        status=str(report.status),
        checked_at=report.checked_at.isoformat(),
        summary=report.summary,
        components=[
            HealthComponentResponse(
                name=component.name,
                status=str(component.status),
                detail=component.detail,
                metadata={key: value for key, value in component.metadata},
            )
            for component in report.components
        ],
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(
    response: Response,
    dependencies: APIDependencies = Depends(get_api_dependencies),
) -> ReadinessResponse:
    report = cast(ReadinessReportLike, dependencies.readiness_reporter.build_report())
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        service_name=report.service_name,
        ready=report.ready,
        checked_at=report.checked_at.isoformat(),
        summary=report.summary,
        blocking_checks=list(report.blocking_checks),
        checks=[
            ReadinessCheckResponse(
                name=check.name,
                ready=check.ready,
                requirement=str(check.requirement),
                detail=check.detail,
                metadata={key: value for key, value in check.metadata},
            )
            for check in report.checks
        ],
    )


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    responses={
        400: {"model": dict},
        401: {"model": dict},
        403: {"model": dict},
        409: {"model": dict},
        429: {"model": dict},
        500: {"model": dict},
        502: {"model": dict},
        504: {"model": dict},
    },
)
def create_chat_completion(
    request: Request,
    payload: ChatCompletionRequest,
    response: Response,
    dependencies: APIDependencies = Depends(get_api_dependencies),
) -> ChatCompletionResponse:
    services = _services_module()
    domain = _domain_module()
    identity = _resolve_submission_identity(
        request=request,
        dependencies=dependencies,
        requested_tenant_id=payload.tenant_id,
    )
    tenant_id = cast(Any, identity.tenant_id)
    request_id = (
        None
        if payload.request_id is None
        else domain.RequestId(tenant_id=tenant_id, value=payload.request_id)
    )
    trace_context = _observability_module().TraceContext.new(
        tenant_id=tenant_id,
        request_id=request_id,
        metadata=_request_trace_metadata(identity),
    )
    submit_result = cast(
        SubmitResultLike,
        dependencies.orchestrator.submit(
            services.ExecutionSubmitRequest(
                tenant_id=tenant_id,
                idempotency_key=domain.IdempotencyKey(
                    payload.idempotency_key
                    or _default_idempotency_key(
                        payload, tenant_id_value=tenant_id.value
                    )
                ),
                request_id=request_id,
                gateway_request=_gateway_request_from_payload(
                    payload, tenant_id, trace_context
                ),
                sandbox_program=dependencies.execution_template.sandbox_program,
                sandbox_resources=dependencies.execution_template.sandbox_resources,
                desired_isolation=dependencies.execution_template.desired_isolation,
                timeouts=_timeouts_from_payload(payload),
                trace_context=trace_context,
            )
        ),
    )
    api_response = _chat_completion_response(
        dependencies=dependencies,
        job=submit_result.job,
        model=payload.model,
        idempotent_replay=submit_result.idempotent_replay,
        cleanup_performed=submit_result.cleanup_performed,
    )
    if submit_result.job.state.status in {
        domain.ExecutionStatus.RECEIVED,
        domain.ExecutionStatus.VALIDATED,
        domain.ExecutionStatus.QUEUED,
        domain.ExecutionStatus.STARTING,
        domain.ExecutionStatus.RUNNING,
        domain.ExecutionStatus.CANCELLING,
    }:
        response.status_code = status.HTTP_202_ACCEPTED
        return api_response
    if (
        submit_result.job.result is not None
        and submit_result.job.result.error is not None
    ):
        raise map_error_details(
            submit_result.job.result.error,
            tenant_id=tenant_id.value,
            request_id=submit_result.job.request.request_id.value,
            job_id=submit_result.job.request.job_id.value,
        )
    return api_response


@router.get("/v1/chat/completions/{job_id}", response_model=ChatCompletionResponse)
def get_chat_completion_status(
    request: Request,
    job_id: str,
    tenant_id: str | None = Header(default=None, alias="X-Agentsty-Tenant-Id"),
    dependencies: APIDependencies = Depends(get_api_dependencies),
) -> ChatCompletionResponse:
    identity = _resolve_job_identity(
        request=request,
        dependencies=dependencies,
        requested_tenant_id=tenant_id,
    )
    record = _job_record(
        dependencies=dependencies,
        tenant_id_value=cast(Any, identity.tenant_id).value,
        job_id_value=job_id,
    )
    poll_result = cast(
        PollResultLike,
        dependencies.orchestrator.poll(
            cast(Any, identity.tenant_id),
            cast(Any, record.request.job_id),
        ),
    )
    return _chat_completion_response(
        dependencies=dependencies,
        job=poll_result.job,
        model=poll_result.job.request.payload.target.model,
        idempotent_replay=False,
        cleanup_performed=poll_result.cleanup_performed,
    )


@router.post(
    "/v1/chat/completions/{job_id}/cancel",
    response_model=CancellationResponse,
)
def cancel_chat_completion(
    request: Request,
    job_id: str,
    response: Response,
    tenant_id: str | None = Header(default=None, alias="X-Agentsty-Tenant-Id"),
    cancellation_reason: str | None = Header(
        default=None, alias="X-Agentsty-Cancel-Reason"
    ),
    dependencies: APIDependencies = Depends(get_api_dependencies),
) -> CancellationResponse:
    services = _services_module()
    domain = _domain_module()
    identity = _resolve_job_identity(
        request=request,
        dependencies=dependencies,
        requested_tenant_id=tenant_id,
    )
    tenant = cast(Any, identity.tenant_id)
    cancellation = cast(
        CancellationResultLike,
        dependencies.orchestrator.cancel(
            services.ExecutionCancellationRequest(
                tenant_id=tenant,
                job_id=domain.JobId(tenant_id=tenant, value=job_id),
                reason=cancellation_reason,
                trace_context=_observability_module().TraceContext.new(
                    tenant_id=tenant,
                    metadata=_request_trace_metadata(
                        identity, transport="fastapi.cancel"
                    ),
                ),
            )
        ),
    )
    if (
        cancellation.job.result is not None
        and cancellation.job.result.error is not None
    ):
        error = ErrorResponseBody(
            message=cancellation.job.result.error.message,
            category=str(cancellation.job.result.error.category),
            code=cancellation.job.result.error.code
            or str(cancellation.job.result.error.category),
            retryable=cancellation.job.result.error.retryable,
            metadata={
                key: value for key, value in cancellation.job.result.error.metadata
            },
        )
    else:
        error = None
    if cancellation.cancellation_requested:
        response.status_code = status.HTTP_202_ACCEPTED
    return CancellationResponse(
        tenant_id=tenant.value,
        request_id=cancellation.job.request.request_id.value,
        job_id=cancellation.job.request.job_id.value,
        status=str(cancellation.job.state.status),
        cancellation_requested=cancellation.cancellation_requested,
        cleanup_performed=cancellation.cleanup_performed,
        error=error,
    )


def _default_idempotency_key(
    payload: ChatCompletionRequest, *, tenant_id_value: str
) -> str:
    return (
        payload.request_id
        or f"submit:{tenant_id_value}:{payload.model}:{len(payload.messages)}"
    )


def _gateway_request_from_payload(
    payload: ChatCompletionRequest,
    tenant_id: object,
    trace_context: object,
) -> object:
    gateway = _gateway_module()
    target = gateway.GatewayModelTarget(model=payload.model, provider=payload.provider)
    return gateway.GatewayRequest(
        tenant_id=tenant_id,
        target=target,
        messages=tuple(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole(message.role),
                content=message.content,
                name=message.name,
            )
            for message in payload.messages
        ),
        allowlist=gateway.GatewayAllowlist(
            allowed_providers=() if payload.provider is None else (payload.provider,),
            allowed_models=(payload.model,),
        ),
        sampling=gateway.GatewaySampling(
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
            stop_sequences=tuple(payload.stop),
        ),
        request_timeout_seconds=payload.request_timeout_seconds,
        trace_context=trace_context,
        metadata=(("transport", "fastapi"),),
    )


def _timeouts_from_payload(payload: ChatCompletionRequest) -> object:
    domain = _domain_module()
    return domain.ExecutionTimeouts(
        request_timeout_seconds=payload.request_timeout_seconds or 60,
        execution_timeout_seconds=payload.execution_timeout_seconds or 900,
        cancellation_grace_period_seconds=payload.cancellation_grace_period_seconds
        or 30,
    )


def _job_record(
    *, dependencies: APIDependencies, tenant_id_value: str, job_id_value: str
) -> JobRecordLike:
    domain = _domain_module()
    tenant_id = domain.TenantId(tenant_id_value)
    job_id = domain.JobId(tenant_id=tenant_id, value=job_id_value)
    return cast(JobRecordLike, dependencies.orchestrator.get_status(tenant_id, job_id))


def _resolve_submission_identity(
    *, request: Request, dependencies: APIDependencies, requested_tenant_id: str
) -> EffectiveRequestIdentity:
    try:
        return resolve_submission_identity(
            request=request,
            settings=cast(Any, dependencies.settings),
            verifier=dependencies.principal_verifier,
            requested_tenant_id=requested_tenant_id,
        )
    except Exception as error:
        raise _map_auth_error(error) from error


def _resolve_job_identity(
    *, request: Request, dependencies: APIDependencies, requested_tenant_id: str | None
) -> EffectiveRequestIdentity:
    try:
        return resolve_job_identity(
            request=request,
            settings=cast(Any, dependencies.settings),
            verifier=dependencies.principal_verifier,
            requested_tenant_id=requested_tenant_id,
        )
    except Exception as error:
        raise _map_auth_error(error) from error


def _map_auth_error(error: Exception) -> Exception:
    domain = _domain_module()
    if isinstance(error, domain.DomainError):
        return map_error_details(error.as_details())
    return error


def _request_trace_metadata(
    identity: EffectiveRequestIdentity, *, transport: str = "fastapi"
) -> tuple[tuple[str, str], ...]:
    principal_subject = identity.principal_subject
    auth_mode = identity.auth_mode
    metadata: tuple[tuple[str, str], ...] = (
        ("transport", transport),
        ("auth_mode", auth_mode),
    )
    if isinstance(principal_subject, str) and principal_subject:
        metadata = metadata + (("principal_subject", principal_subject),)
    return metadata


def _chat_completion_response(
    *,
    dependencies: APIDependencies,
    job: JobRecordLike,
    model: str,
    idempotent_replay: bool,
    cleanup_performed: bool,
) -> ChatCompletionResponse:
    result = job.result
    usage = None
    choices: list[ChatCompletionChoice] = []
    error = None
    if result is not None and result.payload is not None:
        payload = result.payload
        choices.append(
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionChoiceMessage(
                    role=str(payload.message.role),
                    content=payload.message.content,
                    name=payload.message.name,
                ),
                finish_reason=str(payload.finish_reason),
            )
        )
        usage = UsageResponse(
            prompt_tokens=payload.usage.input_tokens,
            completion_tokens=payload.usage.output_tokens,
            total_tokens=payload.usage.total_tokens,
        )
    if result is not None and result.error is not None:
        details = result.error
        error = ErrorResponseBody(
            message=details.message,
            category=str(details.category),
            code=details.code or str(details.category),
            retryable=details.retryable,
            metadata={key: value for key, value in details.metadata},
        )
    artifacts = _artifact_responses(
        cast(
            tuple[ArtifactLike, ...],
            dependencies.orchestrator.list_artifacts(job.tenant_id, job.request.job_id),
        )
    )
    summary = _summary_response(job.state.summary)
    return ChatCompletionResponse(
        id=job.request.job_id.value,
        created=int(job.request.submitted_at.timestamp()),
        model=model,
        tenant_id=job.tenant_id.value,
        request_id=job.request.request_id.value,
        job_id=job.request.job_id.value,
        status=str(job.state.status),
        idempotent_replay=idempotent_replay,
        cleanup_performed=cleanup_performed,
        choices=choices,
        usage=usage,
        summary=summary,
        artifacts=artifacts,
        error=error,
    )


def _summary_response(summary: SummaryLike | None) -> ExecutionSummaryResponse | None:
    if summary is None:
        return None
    return ExecutionSummaryResponse(
        output_text=summary.output_text,
        duration_seconds=summary.duration_seconds,
        artifact_count=summary.artifact_count,
        metadata={key: value for key, value in summary.metadata},
    )


def _artifact_responses(records: tuple[ArtifactLike, ...]) -> list[ArtifactResponse]:
    responses: list[ArtifactResponse] = []
    for record in records:
        artifact = cast(ArtifactSummaryLike, record.artifact)
        storage = record.content_ref
        responses.append(
            ArtifactResponse(
                key=artifact.key,
                media_type=artifact.media_type,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                redacted=artifact.redacted,
                metadata={key: value for key, value in artifact.metadata},
                storage=(
                    None
                    if storage is None
                    else ArtifactContentRefResponse(
                        storage_backend=storage.storage_backend,
                        locator=storage.locator,
                    )
                ),
            )
        )
    return responses

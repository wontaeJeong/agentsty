"""Execution lifecycle orchestration across persistence, runtime, and executor."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config.settings import PlatformSettings
from ..domain.errors import (
    CancellationError,
    DomainError,
    ErrorDetails,
    InternalError,
    RuntimeExecutionError,
    SandboxCreationError,
)
from ..domain.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from ..domain.ids import JobId, TenantId
from ..domain.models import ArtifactSummary, ResultSummary
from ..executors.adapter import SandboxExecutor
from ..executors.contracts import (
    SandboxCancellationRequest,
    SandboxCreateRequest,
    SandboxHandle,
    SandboxInspection,
    SandboxLaunchRequest,
    SandboxProgramSpec,
    SandboxStatus,
)
from ..gateway.contracts import GatewayRequest, GatewayResponse
from ..observability.logging import LogSeverity, StructuredLogger
from ..observability.metrics import MetricRecorder
from ..observability.tracing import TraceContext, attach_trace_context
from ..persistence.models import (
    ArtifactContentRef,
    ArtifactMetadataRecord,
    AuditMetadata,
    JobRecord,
)
from ..persistence.repositories import (
    ArtifactContentStore,
    ArtifactMetadataRepository,
    JobRepository,
)
from ..runtimes.adapter import AgentRuntimeAdapter
from ..runtimes.contracts import (
    RuntimeCancellationRequest,
    RuntimeCollectionRequest,
    RuntimePreparationRequest,
    RuntimeSession,
)
from .cleanup import CleanupCoordinator, CleanupOutcome
from .intake import RequestIntakeService
from .models import (
    ExecutionCancellationRequest,
    ExecutionCancellationResult,
    ExecutionPollResult,
    ExecutionSubmitRequest,
    ExecutionSubmitResult,
)
from .policy import InMemoryPolicyQuotaService, PolicyQuotaService


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _job_key(record: JobRecord[GatewayRequest, GatewayResponse]) -> tuple[str, str]:
    return (record.tenant_id.value, record.request.job_id.value)


@dataclass(slots=True)
class _ActiveExecution:
    sandbox: SandboxHandle
    session: RuntimeSession
    trace_context: TraceContext
    slot_acquired: bool = True


@dataclass(slots=True)
class ExecutionOrchestrator:
    """Transport-agnostic service layer for request intake and execution lifecycle."""

    settings: PlatformSettings
    jobs: JobRepository[GatewayRequest, GatewayResponse]
    artifact_metadata: ArtifactMetadataRepository
    runtime_adapter: AgentRuntimeAdapter
    sandbox_executor: SandboxExecutor
    intake_service: RequestIntakeService
    artifact_content: ArtifactContentStore | None = None
    policy_service: PolicyQuotaService = field(
        default_factory=InMemoryPolicyQuotaService
    )
    logger: StructuredLogger = field(default_factory=StructuredLogger)
    metrics: MetricRecorder = field(default_factory=MetricRecorder)
    cleanup_coordinator: CleanupCoordinator | None = None
    _active_executions: dict[tuple[str, str], _ActiveExecution] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.cleanup_coordinator is None:
            self.cleanup_coordinator = CleanupCoordinator(
                runtime_adapter=self.runtime_adapter,
                sandbox_executor=self.sandbox_executor,
                logger=self.logger,
                metrics=self.metrics,
            )

    def submit(self, request: ExecutionSubmitRequest) -> ExecutionSubmitResult:
        intake = self.intake_service.intake(request)
        if intake.idempotent_replay:
            return ExecutionSubmitResult(
                job=intake.job,
                trace_context=intake.trace_context,
                idempotent_replay=True,
                cleanup_performed=False,
                metadata=(("idempotent_replay", "true"),),
            )

        with attach_trace_context(intake.trace_context):
            cleanup_performed = False
            try:
                record = self.jobs.mark_validated(
                    request.tenant_id,
                    intake.execution.job_id,
                    updated_at=intake.execution.submitted_at,
                    audit_metadata=request.audit_metadata,
                )
                submission_decision = self.policy_service.evaluate_submission(
                    request,
                    trace_context=intake.trace_context,
                )
                submission_decision.require_allowed()
                slot_decision = self.policy_service.acquire_execution_slot(
                    request.tenant_id,
                    intake.execution.job_id,
                    trace_context=intake.trace_context,
                )
                slot_decision.require_allowed()

                queued = self.jobs.mark_queued(
                    request.tenant_id,
                    intake.execution.job_id,
                    audit_metadata=request.audit_metadata,
                )
                session = self.runtime_adapter.prepare(
                    RuntimePreparationRequest(
                        tenant_id=request.tenant_id,
                        request_id=intake.execution.request_id,
                        job_id=intake.execution.job_id,
                        workspace_path=self._workspace_path(
                            intake.execution.job_id,
                            request.sandbox_program,
                        ),
                        trace_context=intake.trace_context,
                        metadata=request.metadata + (("service", "orchestration"),),
                    )
                )
                sandbox = self.sandbox_executor.create(
                    SandboxCreateRequest(
                        tenant_id=request.tenant_id,
                        request_id=intake.execution.request_id,
                        job_id=intake.execution.job_id,
                        program=_sandbox_runtime_program(
                            request.sandbox_program,
                            session=session,
                            execution=intake.execution,
                            trace_context=intake.trace_context,
                            metadata=request.metadata + (("service", "orchestration"),),
                        ),
                        resources=request.sandbox_resources,
                        timeouts=request.timeouts,
                        desired_isolation=request.desired_isolation,
                        metadata=request.metadata + (("service", "orchestration"),),
                    )
                )
                self._active_executions[_job_key(queued)] = _ActiveExecution(
                    sandbox=sandbox,
                    session=session,
                    trace_context=intake.trace_context,
                )

                started_at = _utc_now()
                self.jobs.mark_starting(
                    request.tenant_id,
                    intake.execution.job_id,
                    started_at=started_at,
                    audit_metadata=request.audit_metadata,
                )
                self.sandbox_executor.launch(
                    sandbox,
                    SandboxLaunchRequest(
                        tenant_id=request.tenant_id,
                        request_id=intake.execution.request_id,
                        job_id=intake.execution.job_id,
                        identity=sandbox.identity,
                        requested_at=started_at,
                        metadata=request.metadata + (("service", "orchestration"),),
                    ),
                )
                inspection = self.sandbox_executor.inspect(sandbox)
                if inspection.status.is_terminal:
                    record, cleanup_performed = self._finalize_from_inspection(
                        queued,
                        inspection,
                        trace_context=intake.trace_context,
                        audit_metadata=request.audit_metadata,
                    )
                    return ExecutionSubmitResult(
                        job=record,
                        trace_context=intake.trace_context,
                        cleanup_performed=cleanup_performed,
                    )

                self.jobs.mark_running(
                    request.tenant_id,
                    intake.execution.job_id,
                    updated_at=started_at,
                    audit_metadata=request.audit_metadata,
                )
                poll_result = self._await_initial_poll(
                    request.tenant_id,
                    intake.execution.job_id,
                )
                return ExecutionSubmitResult(
                    job=poll_result.job,
                    trace_context=intake.trace_context,
                    cleanup_performed=poll_result.cleanup_performed,
                )
            except Exception as error:
                record = self._terminalize_submission_error(
                    request,
                    intake.execution.job_id,
                    error,
                    trace_context=intake.trace_context,
                )
                cleanup_performed = record.state.status.is_terminal
                return ExecutionSubmitResult(
                    job=record,
                    trace_context=intake.trace_context,
                    cleanup_performed=cleanup_performed,
                )

    def poll(self, tenant_id: TenantId, job_id: JobId) -> ExecutionPollResult:
        record = self.jobs.get(tenant_id, job_id)
        if record.state.status.is_terminal:
            return ExecutionPollResult(job=record, cleanup_performed=False)

        active = self._active_executions.get(_job_key(record))
        if active is None:
            return ExecutionPollResult(job=record, cleanup_performed=False)

        with attach_trace_context(active.trace_context):
            collection = self.runtime_adapter.collect_result(
                active.session,
                RuntimeCollectionRequest(
                    tenant_id=record.tenant_id,
                    request_id=record.request.request_id,
                    job_id=record.request.job_id,
                    session_id=active.session.session_id,
                    metadata=(("service", "orchestration.poll"),),
                ),
            )
            if collection.ready and collection.result is not None:
                finalized, cleanup_performed = self._finalize_from_runtime_result(
                    record,
                    collection.result,
                    trace_context=active.trace_context,
                )
                return ExecutionPollResult(
                    job=finalized,
                    cleanup_performed=cleanup_performed,
                )

            inspection = self.sandbox_executor.inspect(active.sandbox)
            if inspection.status.is_terminal:
                finalized, cleanup_performed = self._finalize_from_inspection(
                    record,
                    inspection,
                    trace_context=active.trace_context,
                )
                return ExecutionPollResult(
                    job=finalized,
                    cleanup_performed=cleanup_performed,
                )
            return ExecutionPollResult(job=self.jobs.get(tenant_id, job_id))

    def get_status(
        self, tenant_id: TenantId, job_id: JobId
    ) -> JobRecord[GatewayRequest, GatewayResponse]:
        return self.jobs.get(tenant_id, job_id)

    def list_artifacts(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[ArtifactMetadataRecord, ...]:
        return self.artifact_metadata.list_for_job(tenant_id, job_id)

    def cancel(
        self, request: ExecutionCancellationRequest
    ) -> ExecutionCancellationResult:
        record = self.jobs.get(request.tenant_id, request.job_id)
        if record.state.status.is_terminal:
            return ExecutionCancellationResult(
                job=record,
                cancellation_requested=False,
                cleanup_performed=False,
                metadata=(("already_terminal", "true"),),
            )

        active = self._active_executions.get(_job_key(record))
        trace_context = request.trace_context or (
            active.trace_context
            if active is not None
            else TraceContext.new(
                tenant_id=request.tenant_id,
                request_id=record.request.request_id,
                job_id=record.request.job_id,
                metadata=(("service", "orchestration.cancel"),),
            )
        )
        with attach_trace_context(trace_context):
            cancellation_requested = False
            if record.state.status in {
                ExecutionStatus.QUEUED,
                ExecutionStatus.STARTING,
                ExecutionStatus.RUNNING,
            }:
                record = self.jobs.request_cancellation(
                    request.tenant_id,
                    request.job_id,
                    updated_at=request.requested_at,
                    audit_metadata=request.audit_metadata,
                )
                cancellation_requested = True

            if active is None:
                cancelled = self.jobs.mark_cancelled(
                    request.tenant_id,
                    request.job_id,
                    finished_at=request.requested_at,
                    error=CancellationError(
                        request.reason or "execution was cancelled"
                    ).as_details(),
                    summary=ResultSummary(duration_seconds=0.0),
                    audit_metadata=request.audit_metadata,
                )
                self.policy_service.release_execution_slot(
                    request.tenant_id, request.job_id
                )
                return ExecutionCancellationResult(
                    job=cancelled,
                    cancellation_requested=True,
                    cleanup_performed=False,
                )

            self.runtime_adapter.request_cancellation(
                active.session,
                RuntimeCancellationRequest(
                    tenant_id=request.tenant_id,
                    request_id=record.request.request_id,
                    job_id=request.job_id,
                    session_id=active.session.session_id,
                    reason=request.reason,
                    requested_at=request.requested_at,
                    metadata=request.metadata + (("service", "orchestration.cancel"),),
                ),
            )
            self.sandbox_executor.request_cancellation(
                active.sandbox,
                SandboxCancellationRequest(
                    tenant_id=request.tenant_id,
                    request_id=record.request.request_id,
                    job_id=request.job_id,
                    identity=active.sandbox.identity,
                    reason=request.reason,
                    requested_at=request.requested_at,
                    metadata=request.metadata + (("service", "orchestration.cancel"),),
                ),
            )
            poll_result = self.poll(request.tenant_id, request.job_id)
            return ExecutionCancellationResult(
                job=poll_result.job,
                cancellation_requested=cancellation_requested or True,
                cleanup_performed=poll_result.cleanup_performed,
            )

    def _workspace_path(self, job_id: JobId, program: object) -> Path:
        working_directory = getattr(program, "working_directory", None)
        if isinstance(working_directory, str) and working_directory.strip():
            return Path(working_directory)
        return self.settings.runtime.workspace_root / job_id.value

    def _await_initial_poll(
        self,
        tenant_id: TenantId,
        job_id: JobId,
    ) -> ExecutionPollResult:
        attempts = 20
        result = self.poll(tenant_id, job_id)
        for index in range(attempts):
            if index > 0:
                result = self.poll(tenant_id, job_id)
            if result.job.state.status.is_terminal:
                return result
            if index < attempts - 1:
                time.sleep(0.01)
        return result

    def _terminalize_submission_error(
        self,
        request: ExecutionSubmitRequest,
        job_id: JobId,
        error: Exception,
        *,
        trace_context: TraceContext,
    ) -> JobRecord[GatewayRequest, GatewayResponse]:
        details = _coerce_error_details(error, phase="submission")
        current = self.jobs.get(request.tenant_id, job_id)
        if current.state.status.is_terminal:
            return current
        if current.state.status is ExecutionStatus.RECEIVED:
            current = self.jobs.mark_validated(
                request.tenant_id,
                job_id,
                audit_metadata=request.audit_metadata,
            )
        finished_at = _utc_now()
        failed = self.jobs.mark_failed(
            request.tenant_id,
            job_id,
            finished_at=finished_at,
            error=details,
            summary=ResultSummary(
                duration_seconds=max(
                    0.0,
                    (finished_at - current.request.submitted_at).total_seconds(),
                )
            ),
            audit_metadata=request.audit_metadata,
        )
        self._log_terminal(failed, trace_context)
        active = self._active_executions.pop(_job_key(failed), None)
        if active is not None:
            self._run_cleanup(
                active, metadata=(("terminal_status", failed.state.status.value),)
            )
        self.policy_service.release_execution_slot(request.tenant_id, job_id)
        return failed

    def _finalize_from_runtime_result(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        result: ExecutionResult[GatewayResponse],
        *,
        trace_context: TraceContext,
    ) -> tuple[JobRecord[GatewayRequest, GatewayResponse], bool]:
        finalized = self._persist_terminal_result(record, result)
        self._persist_artifacts(finalized, result.artifacts)
        cleanup_performed = self._cleanup_active(finalized, trace_context)
        self._log_terminal(finalized, trace_context)
        return finalized, cleanup_performed

    def _finalize_from_inspection(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        inspection: SandboxInspection,
        *,
        trace_context: TraceContext,
        audit_metadata: AuditMetadata | None = None,
    ) -> tuple[JobRecord[GatewayRequest, GatewayResponse], bool]:
        result = _runtime_result_from_inspection(record, inspection)
        finalized = self._persist_terminal_result(
            record,
            result,
            audit_metadata=audit_metadata,
        )
        cleanup_performed = self._cleanup_active(finalized, trace_context)
        self._log_terminal(finalized, trace_context)
        return finalized, cleanup_performed

    def _persist_terminal_result(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        result: ExecutionResult[GatewayResponse],
        *,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[GatewayRequest, GatewayResponse]:
        if result.status is ExecutionStatus.SUCCEEDED:
            return self.jobs.mark_succeeded(
                record.tenant_id,
                record.request.job_id,
                finished_at=result.completed_at,
                payload=result.payload,
                summary=result.summary,
                artifacts=result.artifacts,
                audit_metadata=audit_metadata,
            )
        assert result.error is not None
        if result.status is ExecutionStatus.TIMED_OUT:
            return self.jobs.mark_timed_out(
                record.tenant_id,
                record.request.job_id,
                finished_at=result.completed_at,
                error=result.error,
                summary=result.summary,
                audit_metadata=audit_metadata,
            )
        if result.status is ExecutionStatus.CANCELLED:
            return self.jobs.mark_cancelled(
                record.tenant_id,
                record.request.job_id,
                finished_at=result.completed_at,
                error=result.error,
                summary=result.summary,
                audit_metadata=audit_metadata,
            )
        return self.jobs.mark_failed(
            record.tenant_id,
            record.request.job_id,
            finished_at=result.completed_at,
            error=result.error,
            summary=result.summary,
            audit_metadata=audit_metadata,
        )

    def _persist_artifacts(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        artifacts: tuple[ArtifactSummary, ...],
    ) -> None:
        active = self._active_executions.get(_job_key(record))
        for artifact in artifacts:
            content_ref = self._persist_artifact_content(
                record,
                artifact,
                session_workspace=(
                    None if active is None else active.session.workspace_path
                ),
            )
            _ = self.artifact_metadata.put(
                ArtifactMetadataRecord(
                    tenant_id=record.tenant_id,
                    job_id=record.request.job_id,
                    artifact=artifact,
                    created_at=record.state.finished_at or _utc_now(),
                    content_ref=content_ref,
                )
            )

    def _persist_artifact_content(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        artifact: ArtifactSummary,
        *,
        session_workspace: Path | None,
    ) -> ArtifactContentRef | None:
        if self.artifact_content is None or session_workspace is None:
            return None
        source_path = _runtime_artifact_path(session_workspace, artifact.key)
        return self.artifact_content.write(
            record.tenant_id,
            record.request.job_id,
            artifact.key,
            source_path.read_bytes(),
        )

    def _cleanup_active(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        trace_context: TraceContext,
    ) -> bool:
        active = self._active_executions.pop(_job_key(record), None)
        if active is None:
            self.policy_service.release_execution_slot(
                record.tenant_id,
                record.request.job_id,
            )
            return False
        self._run_cleanup(
            active,
            metadata=(("terminal_status", record.state.status.value),),
        )
        self.policy_service.release_execution_slot(
            record.tenant_id, record.request.job_id
        )
        return True

    def _run_cleanup(
        self,
        active: _ActiveExecution,
        *,
        metadata: tuple[tuple[str, str], ...],
    ) -> CleanupOutcome:
        assert self.cleanup_coordinator is not None
        return self.cleanup_coordinator.cleanup(
            sandbox=active.sandbox,
            session=active.session,
            trace_context=active.trace_context,
            metadata=metadata,
        )

    def _log_terminal(
        self,
        record: JobRecord[GatewayRequest, GatewayResponse],
        trace_context: TraceContext,
    ) -> None:
        self.logger.emit(
            "services.execution.completed",
            f"execution reached terminal state {record.state.status.value}",
            severity=(
                LogSeverity.INFO
                if record.state.status is ExecutionStatus.SUCCEEDED
                else LogSeverity.WARNING
            ),
            trace_context=trace_context,
            attributes={
                "status": record.state.status.value,
                "tenant_id": record.tenant_id.value,
                "job_id": record.request.job_id.value,
            },
        )
        if record.state.finished_at is not None:
            self.metrics.record_duration(
                "agentsty.services.execution.duration",
                max(
                    0.0,
                    (
                        record.state.finished_at - record.request.submitted_at
                    ).total_seconds(),
                ),
                attributes={"status": record.state.status.value},
                trace_context=trace_context,
            )


def _coerce_error_details(error: Exception, *, phase: str) -> ErrorDetails:
    if isinstance(error, DomainError):
        return error.as_details()
    message = str(error) or f"{phase} failed"
    if phase == "submission":
        return SandboxCreationError(message).as_details()
    if phase == "runtime":
        return RuntimeExecutionError(message).as_details()
    return InternalError(message).as_details()


def _runtime_artifact_path(workspace_path: Path, artifact_key: str) -> Path:
    cleaned_key = artifact_key.strip()
    artifact_path = Path(cleaned_key)
    if not cleaned_key or artifact_path.is_absolute() or ".." in artifact_path.parts:
        raise ValueError("artifact key must resolve to a safe relative path")
    return workspace_path.joinpath(
        ".agentsty-runtime", "artifacts", *artifact_path.parts
    )


def _runtime_result_from_inspection(
    record: JobRecord[GatewayRequest, GatewayResponse],
    inspection: SandboxInspection,
) -> ExecutionResult[GatewayResponse]:
    completed_at = inspection.finished_at or inspection.observed_at
    if inspection.status is SandboxStatus.SUCCEEDED:
        return ExecutionResult(
            tenant_id=record.tenant_id,
            request_id=record.request.request_id,
            job_id=record.request.job_id,
            status=ExecutionStatus.SUCCEEDED,
            completed_at=completed_at,
            summary=ResultSummary(
                duration_seconds=max(
                    0.0,
                    (completed_at - record.request.submitted_at).total_seconds(),
                )
            ),
        )
    details = (
        inspection.error
        or InternalError(
            inspection.status.value,
            metadata=(("sandbox_status", inspection.status.value),),
        ).as_details()
    )
    status = ExecutionStatus.FAILED
    if inspection.status is SandboxStatus.TIMED_OUT:
        status = ExecutionStatus.TIMED_OUT
    elif inspection.status is SandboxStatus.CANCELLED:
        status = ExecutionStatus.CANCELLED
    return ExecutionResult(
        tenant_id=record.tenant_id,
        request_id=record.request.request_id,
        job_id=record.request.job_id,
        status=status,
        completed_at=completed_at,
        summary=ResultSummary(
            duration_seconds=max(
                0.0,
                (completed_at - record.request.submitted_at).total_seconds(),
            ),
            metadata=(("sandbox_status", inspection.status.value),),
        ),
        error=details,
    )


def _sandbox_runtime_program(
    program: SandboxProgramSpec,
    *,
    session: RuntimeSession,
    execution: ExecutionRequest[GatewayRequest],
    trace_context: TraceContext,
    metadata: tuple[tuple[str, str], ...],
) -> SandboxProgramSpec:
    command = program.command
    args = tuple(program.args)
    if args and args[-1] == "serve":
        args = args[:-1] + ("execute",)
    payload = json.dumps(
        {
            "tenant_id": session.tenant_id.value,
            "request_id": session.request_id.value,
            "job_id": session.job_id.value,
            "trace_context": _trace_context_payload(trace_context),
            "session": {
                "runtime_name": session.runtime_name,
                "session_id": session.session_id,
                "workspace_path": str(session.workspace_path),
                "metadata": _metadata_payload(session.metadata),
            },
            "execution": _execution_payload(execution),
            "invocation_metadata": _metadata_payload(metadata),
        },
        separators=(",", ":"),
    )
    return SandboxProgramSpec(
        command=tuple(command),
        args=args,
        environment=tuple(program.environment)
        + (("AGENTSTY_RUNNER_PAYLOAD", payload),),
        working_directory=program.working_directory,
        image_reference=program.image_reference,
    )


def _execution_payload(
    execution: ExecutionRequest[GatewayRequest],
) -> dict[str, object]:
    gateway_request = execution.payload
    return {
        "idempotency_key": execution.idempotency_key.value,
        "submitted_at": execution.submitted_at.isoformat(),
        "timeouts": {
            "request_timeout_seconds": execution.timeouts.request_timeout_seconds,
            "execution_timeout_seconds": execution.timeouts.execution_timeout_seconds,
            "cancellation_grace_period_seconds": execution.timeouts.cancellation_grace_period_seconds,
        },
        "metadata": _metadata_payload(execution.metadata),
        "payload": {
            "provider": gateway_request.target.provider,
            "model": gateway_request.target.model,
            "messages": [
                {
                    "role": getattr(message.role, "value", message.role),
                    "content": message.content,
                    "name": message.name,
                    "metadata": _metadata_payload(message.metadata),
                }
                for message in gateway_request.messages
            ],
            "allowlist": {
                "allowed_providers": list(gateway_request.allowlist.allowed_providers),
                "allowed_models": list(gateway_request.allowlist.allowed_models),
            },
            "sampling": {
                "temperature": gateway_request.sampling.temperature,
                "max_output_tokens": gateway_request.sampling.max_output_tokens,
                "stop_sequences": list(gateway_request.sampling.stop_sequences),
            },
            "request_timeout_seconds": gateway_request.request_timeout_seconds,
            "trace_context": _trace_context_payload(gateway_request.trace_context),
            "metadata": _metadata_payload(gateway_request.metadata),
        },
    }


def _trace_context_payload(
    trace_context: TraceContext | None,
) -> dict[str, object] | None:
    if trace_context is None:
        return None
    return {
        "correlation_id": trace_context.correlation_id,
        "tenant_id": None
        if trace_context.tenant_id is None
        else trace_context.tenant_id.value,
        "request_id": None
        if trace_context.request_id is None
        else trace_context.request_id.value,
        "job_id": None if trace_context.job_id is None else trace_context.job_id.value,
        "trace_id": trace_context.trace_id,
        "span_id": trace_context.span_id,
        "parent_span_id": trace_context.parent_span_id,
        "metadata": _metadata_payload(trace_context.metadata),
    }


def _metadata_payload(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]

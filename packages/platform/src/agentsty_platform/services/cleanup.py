"""Cleanup coordination for runtime and sandbox orchestration resources."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.errors import DomainError, ErrorDetails, InternalError
from ..domain.models import Metadata, normalize_metadata
from ..executors.adapter import SandboxExecutor
from ..executors.contracts import SandboxCleanupRequest, SandboxHandle
from ..observability.logging import LogSeverity, StructuredLogger
from ..observability.metrics import MetricRecorder
from ..observability.tracing import TraceContext
from ..runtimes.adapter import AgentRuntimeAdapter
from ..runtimes.contracts import RuntimeCleanupRequest, RuntimeSession


@dataclass(frozen=True, slots=True)
class CleanupOutcome:
    """Cleanup summary for runtime and sandbox resources."""

    runtime_cleaned: bool = False
    sandbox_cleaned: bool = False
    errors: tuple[ErrorDetails, ...] = ()
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(slots=True)
class CleanupCoordinator:
    """Shared cleanup flow that never overwrites the primary execution outcome."""

    runtime_adapter: AgentRuntimeAdapter
    sandbox_executor: SandboxExecutor
    logger: StructuredLogger
    metrics: MetricRecorder

    def cleanup(
        self,
        *,
        sandbox: SandboxHandle | None,
        session: RuntimeSession | None,
        trace_context: TraceContext,
        metadata: Metadata = (),
    ) -> CleanupOutcome:
        errors: list[ErrorDetails] = []
        runtime_cleaned = False
        sandbox_cleaned = False

        if session is not None:
            try:
                runtime_result = self.runtime_adapter.cleanup(
                    session,
                    RuntimeCleanupRequest(
                        tenant_id=session.tenant_id,
                        request_id=session.request_id,
                        job_id=session.job_id,
                        session_id=session.session_id,
                        metadata=metadata,
                    ),
                )
                runtime_cleaned = runtime_result.cleaned
            except Exception as error:  # pragma: no cover - defensive normalization
                details = _cleanup_error_details(error, component="runtime")
                errors.append(details)
                self.logger.emit(
                    "services.cleanup.runtime_failed",
                    details.message,
                    severity=LogSeverity.ERROR,
                    trace_context=trace_context,
                    attributes={"component": "runtime", "job_id": session.job_id.value},
                )

        if sandbox is not None:
            try:
                sandbox_result = self.sandbox_executor.cleanup(
                    sandbox,
                    SandboxCleanupRequest(
                        tenant_id=sandbox.tenant_id,
                        request_id=sandbox.request_id,
                        job_id=sandbox.job_id,
                        identity=sandbox.identity,
                        metadata=metadata,
                    ),
                )
                sandbox_cleaned = sandbox_result.cleaned
            except Exception as error:  # pragma: no cover - defensive normalization
                details = _cleanup_error_details(error, component="sandbox")
                errors.append(details)
                self.logger.emit(
                    "services.cleanup.sandbox_failed",
                    details.message,
                    severity=LogSeverity.ERROR,
                    trace_context=trace_context,
                    attributes={"component": "sandbox", "job_id": sandbox.job_id.value},
                )

        self.metrics.increment_counter(
            "agentsty.services.cleanup.attempts",
            attributes={
                "runtime_cleaned": str(runtime_cleaned).lower(),
                "sandbox_cleaned": str(sandbox_cleaned).lower(),
                "error_count": str(len(errors)),
            },
            trace_context=trace_context,
        )
        return CleanupOutcome(
            runtime_cleaned=runtime_cleaned,
            sandbox_cleaned=sandbox_cleaned,
            errors=tuple(errors),
            metadata=normalize_metadata(metadata),
        )


def _cleanup_error_details(error: Exception, *, component: str) -> ErrorDetails:
    if isinstance(error, DomainError):
        return error.as_details()
    return InternalError(
        str(error) or f"{component} cleanup failed",
        metadata=(("component", component),),
    ).as_details()

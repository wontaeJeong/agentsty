from agentsty.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    PreparedExecution,
    RuntimeExecutionError,
    SandboxExecutionRecord,
)


class OpenCodeRuntime:
    runtime_name = "opencode"

    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        return PreparedExecution(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            message=request.message,
            metadata=request.metadata or {},
            timeout_seconds=request.timeout_seconds,
            runtime_name=self.runtime_name,
        )

    def build_result(
        self,
        request: ExecutionRequest,
        sandbox_record: SandboxExecutionRecord,
    ) -> ExecutionResult:
        if self._should_fail:
            msg = "OpenCodeRuntime configured to fail"
            raise RuntimeExecutionError(msg)

        generated_text = f"OpenCodeRuntime stub response: {request.message}"
        return ExecutionResult(
            request_id=request.request_id,
            status=sandbox_record.status,
            generated_text=generated_text,
            artifacts=sandbox_record.artifacts,
            runtime_name=self.runtime_name,
            sandbox_execution_id=sandbox_record.sandbox_execution_id,
        )

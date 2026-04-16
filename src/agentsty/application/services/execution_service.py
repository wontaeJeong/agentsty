from agentsty.application.errors import ApplicationExecutionError
from agentsty.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeExecutionError,
    SandboxExecutionError,
)
from agentsty.domain.ports import AgentRuntime, SandboxExecutor


class ExecutionService:
    def __init__(self, runtime: AgentRuntime, sandbox_executor: SandboxExecutor) -> None:
        self._runtime = runtime
        self._sandbox_executor = sandbox_executor

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            prepared_execution = self._runtime.prepare(request)
            sandbox_record = self._sandbox_executor.execute(prepared_execution)
            return self._runtime.build_result(request, sandbox_record)
        except (RuntimeExecutionError, SandboxExecutionError) as exc:
            msg = f"Execution failed: {exc}"
            raise ApplicationExecutionError(msg, status_code=502) from exc

from uuid import uuid4

from agentsty.domain.execution import (
    Artifact,
    PreparedExecution,
    SandboxExecutionError,
    SandboxExecutionRecord,
)


class StubSandboxExecutor:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def execute(self, prepared_execution: PreparedExecution) -> SandboxExecutionRecord:
        if self._should_fail:
            msg = "Stub sandbox configured to fail"
            raise SandboxExecutionError(msg)

        sandbox_execution_id = f"sbx-{uuid4()}"
        output_text = f"sandbox::{prepared_execution.runtime_name}::{prepared_execution.message}"
        artifact = Artifact(name="execution-log", content=output_text)
        return SandboxExecutionRecord(
            sandbox_execution_id=sandbox_execution_id,
            status="completed",
            output_text=output_text,
            artifacts=[artifact],
        )

from __future__ import annotations

from typing import Protocol

from agentsty.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    PreparedExecution,
    SandboxExecutionRecord,
)


class SandboxExecutor(Protocol):
    def execute(self, prepared_execution: PreparedExecution) -> SandboxExecutionRecord: ...


class AgentRuntime(Protocol):
    runtime_name: str

    def prepare(self, request: ExecutionRequest) -> PreparedExecution: ...

    def build_result(
        self,
        request: ExecutionRequest,
        sandbox_record: SandboxExecutionRecord,
    ) -> ExecutionResult: ...

import pytest

from agentsty.application.errors import ApplicationExecutionError
from agentsty.application.services.execution_service import ExecutionService
from agentsty.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    PreparedExecution,
    RuntimeExecutionError,
    SandboxExecutionError,
    SandboxExecutionRecord,
    TenantId,
)


class FakeRuntime:
    runtime_name = "fake"

    def __init__(self, calls: list[str], should_fail: bool = False) -> None:
        self.calls = calls
        self.should_fail = should_fail

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        self.calls.append("prepare")
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
        self.calls.append("build_result")
        if self.should_fail:
            raise RuntimeExecutionError("runtime boom")
        return ExecutionResult(
            request_id=request.request_id,
            status=sandbox_record.status,
            generated_text="ok",
            artifacts=sandbox_record.artifacts,
            runtime_name=self.runtime_name,
            sandbox_execution_id=sandbox_record.sandbox_execution_id,
        )


class FakeSandboxExecutor:
    def __init__(self, calls: list[str], should_fail: bool = False) -> None:
        self.calls = calls
        self.should_fail = should_fail

    def execute(self, prepared_execution: PreparedExecution) -> SandboxExecutionRecord:
        self.calls.append("execute")
        if self.should_fail:
            raise SandboxExecutionError("sandbox boom")
        return SandboxExecutionRecord(
            sandbox_execution_id="sbx-1",
            status="completed",
            output_text=prepared_execution.message,
            artifacts=[],
        )


def make_request() -> ExecutionRequest:
    return ExecutionRequest(
        request_id="req-1",
        tenant_id=TenantId("tenant-a"),
        message="hello",
        metadata={"trace_id": "abc"},
        timeout_seconds=10,
    )


def test_execution_service_calls_dependencies_in_order() -> None:
    calls: list[str] = []
    service = ExecutionService(
        runtime=FakeRuntime(calls), sandbox_executor=FakeSandboxExecutor(calls)
    )

    result = service.execute(make_request())

    assert calls == ["prepare", "execute", "build_result"]
    assert result.status == "completed"


def test_execution_service_normalizes_runtime_failure() -> None:
    calls: list[str] = []
    service = ExecutionService(
        runtime=FakeRuntime(calls, should_fail=True),
        sandbox_executor=FakeSandboxExecutor(calls),
    )

    with pytest.raises(ApplicationExecutionError) as exc_info:
        service.execute(make_request())

    assert exc_info.value.status_code == 502


def test_execution_service_normalizes_sandbox_failure() -> None:
    calls: list[str] = []
    service = ExecutionService(
        runtime=FakeRuntime(calls),
        sandbox_executor=FakeSandboxExecutor(calls, should_fail=True),
    )

    with pytest.raises(ApplicationExecutionError) as exc_info:
        service.execute(make_request())

    assert exc_info.value.status_code == 502

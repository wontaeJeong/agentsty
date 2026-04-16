import pytest

from agentsty.domain.execution import PreparedExecution, SandboxExecutionError, TenantId
from agentsty.infrastructure.executors.stub import StubSandboxExecutor


def make_prepared_execution() -> PreparedExecution:
    return PreparedExecution(
        request_id="req-1",
        tenant_id=TenantId("tenant-a"),
        message="hello",
        metadata={"trace_id": "abc"},
        timeout_seconds=10,
        runtime_name="opencode",
    )


def test_stub_sandbox_executor_returns_execution_record() -> None:
    executor = StubSandboxExecutor()

    record = executor.execute(make_prepared_execution())

    assert record.status == "completed"
    assert record.sandbox_execution_id.startswith("sbx-")
    assert record.output_text == "sandbox::opencode::hello"
    assert record.artifacts[0].content == "sandbox::opencode::hello"


def test_stub_sandbox_executor_failure_path() -> None:
    executor = StubSandboxExecutor(should_fail=True)

    with pytest.raises(SandboxExecutionError):
        executor.execute(make_prepared_execution())

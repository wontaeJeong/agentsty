import pytest

from agentsty.domain.execution import (
    ExecutionRequest,
    RuntimeExecutionError,
    SandboxExecutionRecord,
    TenantId,
)
from agentsty.infrastructure.runtimes.opencode import OpenCodeRuntime


def make_request() -> ExecutionRequest:
    return ExecutionRequest(
        request_id="req-1",
        tenant_id=TenantId("tenant-a"),
        message="hello",
        metadata={"trace_id": "abc"},
        timeout_seconds=10,
    )


def make_record() -> SandboxExecutionRecord:
    return SandboxExecutionRecord(
        sandbox_execution_id="sbx-1",
        status="completed",
        output_text="sandbox::opencode::hello",
        artifacts=[],
    )


def test_opencode_runtime_prepare_and_build_result() -> None:
    runtime = OpenCodeRuntime()
    request = make_request()

    prepared = runtime.prepare(request)
    result = runtime.build_result(request, make_record())

    assert prepared.runtime_name == "opencode"
    assert prepared.request_id == "req-1"
    assert result.generated_text == "OpenCodeRuntime stub response: hello"
    assert result.sandbox_execution_id == "sbx-1"


def test_opencode_runtime_failure_path() -> None:
    runtime = OpenCodeRuntime(should_fail=True)

    with pytest.raises(RuntimeExecutionError):
        runtime.build_result(make_request(), make_record())

from agentsty.domain.execution import (
    Artifact,
    ExecutionRequest,
    ExecutionResult,
    PreparedExecution,
    SandboxExecutionRecord,
    TenantId,
)


def test_domain_models_hold_expected_values() -> None:
    tenant_id = TenantId("tenant-a")
    request = ExecutionRequest(
        request_id="req-1",
        tenant_id=tenant_id,
        message="hello",
        metadata={"trace_id": "abc"},
        timeout_seconds=15,
    )
    artifact = Artifact(name="log", content="output")
    prepared = PreparedExecution(
        request_id=request.request_id,
        tenant_id=request.tenant_id,
        message=request.message,
        metadata=request.metadata or {},
        timeout_seconds=request.timeout_seconds,
        runtime_name="opencode",
    )
    record = SandboxExecutionRecord(
        sandbox_execution_id="sbx-1",
        status="completed",
        output_text="sandbox::opencode::hello",
        artifacts=[artifact],
    )
    result = ExecutionResult(
        request_id=request.request_id,
        status=record.status,
        generated_text="response",
        artifacts=record.artifacts,
        runtime_name="opencode",
        sandbox_execution_id=record.sandbox_execution_id,
    )

    assert tenant_id == "tenant-a"
    assert request.metadata == {"trace_id": "abc"}
    assert prepared.runtime_name == "opencode"
    assert result.generated_text == "response"
    assert result.runtime_name == "opencode"
    assert result.sandbox_execution_id == "sbx-1"

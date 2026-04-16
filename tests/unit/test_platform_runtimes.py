from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


def _runtimes_module() -> Any:
    return importlib.import_module("agentsty_platform.runtimes")


@pytest.mark.unit
def test_runtime_contract_public_exports_model_headless_lifecycle() -> None:
    domain = _domain_module()
    gateway = _gateway_module()
    observability = _observability_module()
    runtimes = _runtimes_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
    )
    prepared_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 16, 12, 0, 5, tzinfo=UTC)

    preparation = runtimes.RuntimePreparationRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        workspace_path=Path("/tmp/runtime/tenant-a/job-1"),
        trace_context=trace_context,
        metadata=(("adapter", "test-double"),),
    )
    session = runtimes.RuntimeSession(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        runtime_name="test-double",
        session_id="session-1",
        workspace_path=preparation.workspace_path,
        capabilities=runtimes.RuntimeCapabilities(),
        prepared_at=prepared_at,
        trace_context=trace_context,
    )
    execution = domain.ExecutionRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        idempotency_key=domain.IdempotencyKey("idem-1"),
        payload=gateway.GatewayRequest(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
            messages=(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.USER,
                    content="hello runtime",
                ),
            ),
            trace_context=trace_context,
        ),
    )
    invocation = runtimes.RuntimeInvocationRequest(execution=execution)
    receipt = runtimes.RuntimeInvocationReceipt(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        session_id=session.session_id,
        accepted_at=prepared_at,
    )
    result = domain.ExecutionResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.SUCCEEDED,
        completed_at=completed_at,
        payload=gateway.GatewayResponse(
            tenant_id=tenant,
            target=execution.payload.target,
            message=gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.ASSISTANT,
                content="headless success",
            ),
        ),
        summary=domain.ResultSummary(output_text="headless success"),
    )
    collected = runtimes.RuntimeCollectionResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        session_id=session.session_id,
        ready=True,
        result=result,
    )
    cancellation = runtimes.RuntimeCancellationRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        session_id=session.session_id,
        reason="operator stop",
    )
    cleanup = runtimes.RuntimeCleanupResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        session_id=session.session_id,
        cleaned=True,
        released_paths=(str(session.workspace_path),),
    )

    assert preparation.trace_context == trace_context
    assert (
        session.capabilities.automation_mode is runtimes.RuntimeAutomationMode.HEADLESS
    )
    assert session.capabilities.uses_internal_gateway is True
    assert invocation.execution.payload.messages[0].content == "hello runtime"
    assert receipt.session_id == session.session_id
    assert collected.result.payload.message.content == "headless success"
    assert cancellation.reason == "operator stop"
    assert cleanup.released_paths == ("/tmp/runtime/tenant-a/job-1",)


@pytest.mark.unit
def test_runtime_collection_contract_rejects_ready_mismatch() -> None:
    domain = _domain_module()
    runtimes = _runtimes_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    completed_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    error = domain.RuntimeExecutionError("not ready").as_details()
    result = domain.ExecutionResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.FAILED,
        completed_at=completed_at,
        error=error,
    )

    with pytest.raises(ValueError, match="non-ready runtime collection results"):
        _ = runtimes.RuntimeCollectionResult(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            session_id="session-1",
            ready=False,
            result=result,
        )


@pytest.mark.unit
def test_runtime_factory_builds_configured_adapter_without_hardcoded_call_site_imports() -> (
    None
):
    config = importlib.import_module("agentsty_platform.config")
    gateway = _gateway_module()
    runtimes = _runtimes_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=gateway.LocalGatewayTransport(),
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )

    adapter = runtimes.build_runtime_adapter(settings, gateway_client)
    inline_adapter = runtimes.build_runtime_adapter_from_env(
        settings,
        gateway_client,
        environ={"AGENTSTY_RUNNER_COMMAND_RUNNER": "inline"},
    )

    assert adapter.runtime_name == "opencode"
    assert inline_adapter.runtime_name == "opencode"
    assert type(inline_adapter.command_runner).__name__ == "InlineCommandRunner"

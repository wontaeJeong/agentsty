from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from tests.runtime_opencode_support import (
    FakeCommandRunner,
    build_guarded_gateway_client,
)

from .support import (
    config_module,
    domain_module,
    gateway_module,
    observability_module,
    runtime_package,
    runtimes_module,
)

pytestmark = pytest.mark.integration


def test_opencode_runtime_adapter_uses_real_gateway_client_for_managed_auth_context() -> (
    None
):
    config = config_module()
    domain = domain_module()
    gateway = gateway_module()
    observability = observability_module()
    runtimes = runtimes_module()
    opencode = runtime_package()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
    )
    client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    runner = FakeCommandRunner(assistant_text="adapter completed")
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=client,
        runtime_settings=settings.runtime,
        command_runner=runner,
    )
    gateway_request = gateway.GatewayRequest(
        tenant_id=tenant,
        target=gateway.GatewayModelTarget(
            provider="internal-openai",
            model="gpt-4o-mini",
        ),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="hello from adapter",
            ),
        ),
        trace_context=trace_context,
    )

    session = adapter.prepare(
        runtimes.RuntimePreparationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            workspace_path=Path("/tmp/opencode/job-1"),
            trace_context=trace_context,
        )
    )
    _ = adapter.invoke(
        session,
        runtimes.RuntimeInvocationRequest(
            execution=domain.ExecutionRequest(
                tenant_id=tenant,
                request_id=request_id,
                job_id=job_id,
                idempotency_key=domain.IdempotencyKey("idem-1"),
                payload=gateway_request,
            )
        ),
    )
    collected = adapter.collect_result(session)
    cleanup = adapter.cleanup(session)

    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.SUCCEEDED
    assert collected.result.payload.message.content == "adapter completed"
    assert client.calls == []
    assert len(runner.run_calls) == 1
    assert runner.managed_config is not None
    managed_config = runner.managed_config
    provider_map = cast(dict[str, object], managed_config["provider"])
    provider = cast(dict[str, object], provider_map["internal-openai"])
    provider_models = cast(dict[str, object], provider["models"])
    headers = cast(
        dict[str, str],
        cast(dict[str, object], provider_models["gpt-4o-mini"])["headers"],
    )
    assert headers["X-Agentsty-Tenant"] == "tenant-a"
    assert headers["Authorization"].startswith("Bearer ")
    assert cleanup.released_paths == ("/tmp/opencode/job-1",)


def test_opencode_runtime_cancellation_short_circuits_cli_integration_path() -> None:
    config = config_module()
    domain = domain_module()
    gateway = gateway_module()
    runtimes = runtimes_module()
    opencode = runtime_package()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-2")
    job_id = domain.JobId(tenant_id=tenant, value="job-2")
    client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    runner = FakeCommandRunner(assistant_text="should not be used")
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=client,
        runtime_settings=settings.runtime,
        command_runner=runner,
    )
    session = adapter.prepare(
        runtimes.RuntimePreparationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            workspace_path=Path("/tmp/opencode/job-2"),
        )
    )

    cancellation = adapter.request_cancellation(
        session,
        runtimes.RuntimeCancellationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            session_id=session.session_id,
            reason="cancel before invoke",
            requested_at=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
        ),
    )
    _ = adapter.invoke(
        session,
        runtimes.RuntimeInvocationRequest(
            execution=domain.ExecutionRequest(
                tenant_id=tenant,
                request_id=request_id,
                job_id=job_id,
                idempotency_key=domain.IdempotencyKey("idem-2"),
                payload=gateway.GatewayRequest(
                    tenant_id=tenant,
                    target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
                    messages=(
                        gateway.GatewayMessage(
                            role=gateway.GatewayMessageRole.USER,
                            content="this should not reach the runtime",
                        ),
                    ),
                ),
            )
        ),
    )
    collected = adapter.collect_result(
        session,
        runtimes.RuntimeCollectionRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            session_id=session.session_id,
        ),
    )

    assert cancellation.acknowledged is True
    assert runner.serve_calls == []
    assert runner.run_calls == []
    assert runner.export_calls == []
    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.CANCELLED
    assert collected.result.error.category is domain.ErrorCategory.CANCELLATION

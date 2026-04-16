from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.runtime_opencode_support import (
    FakeCommandRunner,
    build_guarded_gateway_client,
)


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


def _runtimes_module() -> Any:
    return importlib.import_module("agentsty_platform.runtimes")


def _opencode_module() -> Any:
    return importlib.import_module("agentsty_runtime_opencode")


def test_opencode_runtime_adapter_executes_real_cli_path_with_managed_config() -> None:
    config = _config_module()
    domain = _domain_module()
    gateway = _gateway_module()
    observability = _observability_module()
    runtimes = _runtimes_module()
    opencode = _opencode_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
    )
    gateway_request = gateway.GatewayRequest(
        tenant_id=tenant,
        target=gateway.GatewayModelTarget(
            provider="internal-openai", model="gpt-4o-mini"
        ),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.SYSTEM,
                content="follow instructions",
            ),
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="hello from adapter",
            ),
        ),
        trace_context=trace_context,
    )
    runner = FakeCommandRunner(assistant_text="adapter completed")
    guarded_client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=guarded_client,
        runtime_settings=settings.runtime,
        command_runner=runner,
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
    receipt = adapter.invoke(
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

    assert opencode.OPENCODE_RUNTIME_NAME == "opencode"
    assert adapter.runtime_name == "opencode"
    assert (
        adapter.capabilities.automation_mode is runtimes.RuntimeAutomationMode.HEADLESS
    )
    assert adapter.capabilities.uses_internal_gateway is True
    assert receipt.automation_mode is runtimes.RuntimeAutomationMode.HEADLESS
    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.SUCCEEDED
    assert collected.result.payload.message.content == "adapter completed"
    assert collected.result.summary.output_text == "adapter completed"
    assert collected.result.summary.artifact_count == 1
    assert collected.result.artifacts[0].key == "opencode/session-export.json"
    assert collected.result.artifacts[0].media_type == "application/json"
    assert collected.result.artifacts[0].size_bytes > 0
    assert collected.result.artifacts[0].sha256 is not None
    assert cleanup.released_paths == ("/tmp/opencode/job-1",)
    assert guarded_client.calls == []

    assert len(runner.serve_calls) == 1
    assert len(runner.run_calls) == 1
    assert len(runner.export_calls) == 1
    serve_args = runner.serve_calls[0].args
    run_args = runner.run_calls[0].args
    assert serve_args[:3] == ("opencode", "serve", "--hostname")
    assert "--port" in serve_args
    assert serve_args[-1] == "--pure"
    assert run_args[:2] == ("opencode", "run")
    assert "--attach" in run_args
    assert "--format" in run_args
    assert "json" in run_args
    assert "--dangerously-skip-permissions" in run_args
    assert "--pure" in run_args
    assert run_args[-1].endswith("hello from adapter")

    assert runner.managed_config is not None
    managed_config = runner.managed_config
    provider = cast(
        dict[str, object],
        cast(dict[str, object], managed_config["provider"])["internal-openai"],
    )
    assert runner.managed_config["enabled_providers"] == ["internal-openai"]
    assert runner.managed_config["model"] == "internal-openai/gpt-4o-mini"
    assert runner.managed_config["permission"] == {
        "question": "allow",
        "plan_enter": "allow",
        "plan_exit": "allow",
    }
    provider_options = cast(dict[str, object], provider["options"])
    provider_models = cast(dict[str, object], provider["models"])
    provider_headers = cast(
        dict[str, str],
        cast(dict[str, object], provider_models["gpt-4o-mini"])["headers"],
    )
    assert provider_options["baseURL"] == "http://127.0.0.1:9000/v1"
    assert provider["id"] == "internal-openai"
    assert (
        cast(dict[str, object], provider_models["gpt-4o-mini"])["id"] == "gpt-4o-mini"
    )
    assert provider_headers["X-Agentsty-Tenant"] == "tenant-a"
    assert provider_headers["Authorization"].startswith("Bearer ")

    run_env = runner.run_calls[0].env
    assert json.loads(run_env["OPENCODE_PERMISSION"]) == [
        {"permission": "question", "pattern": "*", "action": "allow"},
        {"permission": "plan_enter", "pattern": "*", "action": "allow"},
        {"permission": "plan_exit", "pattern": "*", "action": "allow"},
    ]
    assert run_env["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
    assert run_env["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
    assert run_env["OPENCODE_DISABLE_DEFAULT_PLUGINS"] == "1"
    assert (
        json.loads(run_env["OPENCODE_CONFIG_CONTENT"])["model"]
        == "internal-openai/gpt-4o-mini"
    )


def test_opencode_runtime_adapter_falls_back_to_session_list_when_run_stdout_has_no_session_id() -> (
    None
):
    config = _config_module()
    domain = _domain_module()
    gateway = _gateway_module()
    runtimes = _runtimes_module()
    opencode = _opencode_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-5")
    job_id = domain.JobId(tenant_id=tenant, value="job-5")
    runner = FakeCommandRunner(
        assistant_text="adapter completed",
        session_list_before=("ses_old",),
        session_list_after=("ses_new", "ses_old"),
        run_stdout="",
    )
    guarded_client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=guarded_client,
        runtime_settings=settings.runtime,
        command_runner=runner,
    )
    session = adapter.prepare(
        runtimes.RuntimePreparationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            workspace_path=Path("/tmp/opencode/job-5"),
        )
    )

    _ = adapter.invoke(
        session,
        runtimes.RuntimeInvocationRequest(
            execution=domain.ExecutionRequest(
                tenant_id=tenant,
                request_id=request_id,
                job_id=job_id,
                idempotency_key=domain.IdempotencyKey("idem-5"),
                payload=gateway.GatewayRequest(
                    tenant_id=tenant,
                    target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
                    messages=(
                        gateway.GatewayMessage(
                            role=gateway.GatewayMessageRole.USER,
                            content="hello fallback",
                        ),
                    ),
                ),
            )
        ),
    )
    collected = adapter.collect_result(session)

    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.SUCCEEDED
    assert collected.result.payload.message.content == "adapter completed"


def test_opencode_runtime_adapter_honors_cancellation_without_cli_invocation() -> None:
    config = _config_module()
    domain = _domain_module()
    gateway = _gateway_module()
    runtimes = _runtimes_module()
    opencode = _opencode_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-2")
    job_id = domain.JobId(tenant_id=tenant, value="job-2")
    runner = FakeCommandRunner(assistant_text="should not be used")
    guarded_client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=guarded_client,
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
                            content="this should not reach opencode",
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
    assert guarded_client.calls == []
    assert runner.serve_calls == []
    assert runner.run_calls == []
    assert runner.export_calls == []
    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.CANCELLED
    assert collected.result.error.category is domain.ErrorCategory.CANCELLATION


def test_opencode_runtime_adapter_maps_export_parse_failures_to_runtime_errors() -> (
    None
):
    config = _config_module()
    domain = _domain_module()
    gateway = _gateway_module()
    runtimes = _runtimes_module()
    opencode = _opencode_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-3")
    job_id = domain.JobId(tenant_id=tenant, value="job-3")
    runner = FakeCommandRunner(assistant_text="")
    guarded_client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=guarded_client,
        runtime_settings=settings.runtime,
        command_runner=runner,
    )
    session = adapter.prepare(
        runtimes.RuntimePreparationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            workspace_path=Path("/tmp/opencode/job-3"),
        )
    )

    _ = adapter.invoke(
        session,
        runtimes.RuntimeInvocationRequest(
            execution=domain.ExecutionRequest(
                tenant_id=tenant,
                request_id=request_id,
                job_id=job_id,
                idempotency_key=domain.IdempotencyKey("idem-3"),
                payload=gateway.GatewayRequest(
                    tenant_id=tenant,
                    target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
                    messages=(
                        gateway.GatewayMessage(
                            role=gateway.GatewayMessageRole.USER,
                            content="will fail export parsing",
                        ),
                    ),
                ),
            )
        ),
    )
    collected = adapter.collect_result(session)

    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.FAILED
    assert collected.result.error.category is domain.ErrorCategory.RUNTIME_FAILURE
    assert "assistant text" in collected.result.error.message.lower()


def test_opencode_runtime_adapter_uses_latest_assistant_message_with_text() -> None:
    config = _config_module()
    domain = _domain_module()
    gateway = _gateway_module()
    runtimes = _runtimes_module()
    opencode = _opencode_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-4")
    job_id = domain.JobId(tenant_id=tenant, value="job-4")
    runner = FakeCommandRunner(
        export_stdout=json.dumps(
            {
                "info": {"id": "ses_runtime_test"},
                "messages": [
                    {
                        "info": {"role": "assistant", "finish": "stop"},
                        "parts": [{"type": "text", "text": "adapter completed"}],
                    },
                    {
                        "info": {
                            "role": "assistant",
                            "error": {
                                "name": "UnknownError",
                                "data": {"message": "The operation timed out."},
                            },
                        },
                        "parts": [{"type": "step-finish", "reason": "error"}],
                    },
                ],
            }
        )
    )
    guarded_client = build_guarded_gateway_client(
        settings,
        gateway.StaticInternalAuthTokenProvider(),
    )
    adapter = opencode.OpenCodeRuntimeAdapter(
        gateway_client=guarded_client,
        runtime_settings=settings.runtime,
        command_runner=runner,
    )
    session = adapter.prepare(
        runtimes.RuntimePreparationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            workspace_path=Path("/tmp/opencode/job-4"),
        )
    )

    _ = adapter.invoke(
        session,
        runtimes.RuntimeInvocationRequest(
            execution=domain.ExecutionRequest(
                tenant_id=tenant,
                request_id=request_id,
                job_id=job_id,
                idempotency_key=domain.IdempotencyKey("idem-4"),
                payload=gateway.GatewayRequest(
                    tenant_id=tenant,
                    target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
                    messages=(
                        gateway.GatewayMessage(
                            role=gateway.GatewayMessageRole.USER,
                            content="hello export parsing",
                        ),
                    ),
                ),
            )
        ),
    )
    collected = adapter.collect_result(session)

    assert collected.ready is True
    assert collected.result.status is domain.ExecutionStatus.SUCCEEDED
    assert collected.result.payload.message.content == "adapter completed"

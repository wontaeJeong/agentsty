from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from pathlib import Path

import pytest

from tests.runtime_opencode_support import FakeCommandRunner

from .support import (
    DeferredRuntimeAdapter,
    TimeoutSandboxExecutor,
    build_submit_request,
    domain_module,
    gateway_module,
    local_settings,
    localdev_module,
    persistence_module,
    runtime_package,
    services_module,
)

pytestmark = pytest.mark.integration


def test_orchestrator_persists_idempotent_happy_path_across_runtime_and_executor(
    tmp_path: Path,
) -> None:
    domain = domain_module()
    gateway = gateway_module()
    persistence = persistence_module()
    services = services_module()
    runtime_pkg = runtime_package()
    localdev = localdev_module()

    settings = local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    transport = gateway.LocalGatewayTransport()
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=transport,
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_pkg.OpenCodeRuntimeAdapter(
            gateway_client=gateway_client,
            runtime_settings=settings.runtime,
            command_runner=FakeCommandRunner(),
        ),
        sandbox_executor=localdev.LocalProcessSandboxExecutor(
            executor_settings=settings.executor,
            workspace_root=settings.runtime.workspace_root,
        ),
        intake_service=services.RequestIntakeService(jobs=jobs),
    )
    tenant = domain.TenantId("tenant-a")
    submit_request = build_submit_request(
        settings,
        tenant,
        key="idem-happy",
        prompt="hello orchestrator",
    )

    first = orchestrator.submit(submit_request)
    second = orchestrator.submit(submit_request)
    audit_events = jobs.list_audit_events(tenant, first.job.request.job_id)

    assert first.job.state.status is domain.ExecutionStatus.SUCCEEDED
    assert first.job.result is not None
    assert first.job.result.payload is not None
    assert first.job.result.payload.message.content.startswith(
        "local gateway echo: hello orchestrator"
    )
    assert first.cleanup_performed is True
    assert second.idempotent_replay is True
    assert second.job.request.job_id == first.job.request.job_id
    artifacts = artifact_metadata.list_for_job(tenant, first.job.request.job_id)
    assert len(artifacts) == 1
    assert artifacts[0].artifact.key == "opencode/session-export.json"
    assert artifacts[0].content_ref is None
    assert [event.event_type for event in audit_events] == [
        "idempotency_reserved",
        "job_created",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
    ]
    assert orchestrator.runtime_adapter.command_runner.run_calls == []


def test_orchestrator_finalizes_timeout_from_executor_inspection(
    tmp_path: Path,
) -> None:
    domain = domain_module()
    persistence = persistence_module()
    services = services_module()

    settings = local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=DeferredRuntimeAdapter(),
        sandbox_executor=TimeoutSandboxExecutor(),
        intake_service=services.RequestIntakeService(jobs=jobs),
    )
    tenant = domain.TenantId("tenant-a")

    result = orchestrator.submit(
        build_submit_request(
            settings,
            tenant,
            key="idem-timeout",
            prompt="sleep until timeout",
        )
    )

    assert result.job.state.status is domain.ExecutionStatus.TIMED_OUT
    assert result.job.result is not None
    assert result.job.result.error is not None
    assert result.job.result.error.category is domain.ErrorCategory.TIMEOUT
    assert result.cleanup_performed is True

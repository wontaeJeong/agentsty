from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any

import pytest


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def test_executor_contract_public_exports_model_generic_lifecycle() -> None:
    domain = _domain_module()
    executors = _executors_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    created_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    deadline_at = datetime(2026, 4, 16, 12, 15, tzinfo=UTC)
    finished_at = datetime(2026, 4, 16, 12, 2, tzinfo=UTC)

    request = executors.SandboxCreateRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        program=executors.SandboxProgramSpec(
            command=("python",),
            args=("-m", "agentsty_platform.runner", "serve"),
            environment=(("MODE", "test"),),
            image_reference="ghcr.io/agentsty/agentsty-sandbox:latest",
        ),
        resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=256,
        ),
        desired_isolation=executors.SandboxIsolationMode.VIRTUAL_MACHINE,
    )
    boundary = executors.TenantResourceBoundary(
        tenant_id=tenant,
        boundary_kind="namespace",
        boundary_name="agentsty-tenant-a",
    )
    identity = executors.SandboxResourceIdentity(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        executor_name="kubernetes-job",
        provider="kubernetes",
        resource_kind="job",
        resource_name="sandbox-job-1",
        boundary=boundary,
    )
    sandbox = executors.SandboxHandle(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        executor_name="kubernetes-job",
        identity=identity,
        program=request.program,
        resources=request.resources,
        timeouts=request.timeouts,
        desired_isolation=request.desired_isolation,
        created_at=created_at,
    )
    launch = executors.SandboxLaunchReceipt(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        identity=identity,
        accepted_at=created_at,
        deadline_at=deadline_at,
    )
    inspection = executors.SandboxInspection(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        identity=identity,
        status=executors.SandboxStatus.SUCCEEDED,
        observed_at=finished_at,
        started_at=created_at,
        finished_at=finished_at,
        deadline_at=deadline_at,
        exit_code=0,
    )
    cancellation = executors.SandboxCancellationRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        identity=identity,
        reason="operator stop",
        requested_at=created_at,
    )
    cleanup = executors.SandboxCleanupResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        identity=identity,
        cleaned=True,
        cleaned_at=finished_at,
        released_resources=("job/agentsty-tenant-a/sandbox-job-1",),
    )

    assert request.program.command == ("python",)
    assert sandbox.identity.boundary.boundary_kind == "namespace"
    assert launch.deadline_at == deadline_at
    assert inspection.status is executors.SandboxStatus.SUCCEEDED
    assert cancellation.reason == "operator stop"
    assert cleanup.released_resources == ("job/agentsty-tenant-a/sandbox-job-1",)


def test_terminal_executor_inspection_requires_matching_error_category() -> None:
    domain = _domain_module()
    executors = _executors_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    boundary = executors.TenantResourceBoundary(
        tenant_id=tenant,
        boundary_kind="namespace",
        boundary_name="agentsty-tenant-a",
    )
    identity = executors.SandboxResourceIdentity(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        executor_name="kubernetes-job",
        provider="kubernetes",
        resource_kind="job",
        resource_name="sandbox-job-1",
        boundary=boundary,
    )

    with pytest.raises(ValueError, match="timed out sandboxes"):
        _ = executors.SandboxInspection(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            identity=identity,
            status=executors.SandboxStatus.TIMED_OUT,
            observed_at=datetime(2026, 4, 16, 12, 2, tzinfo=UTC),
            started_at=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 4, 16, 12, 2, tzinfo=UTC),
            error=domain.RuntimeExecutionError("wrong category").as_details(),
        )

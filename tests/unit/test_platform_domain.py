from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


@pytest.mark.unit
def test_tenant_scoped_identifiers_and_public_exports() -> None:
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-123")
    job_id = domain.JobId(tenant_id=tenant, value="job-456")

    assert str(tenant) == "tenant-a"
    assert request_id.scoped_value == "tenant-a:req-123"
    assert job_id.scoped_value == "tenant-a:job-456"
    assert domain.ExecutionStatus.RUNNING.can_transition_to(
        domain.ExecutionStatus.SUCCEEDED
    )


@pytest.mark.unit
def test_request_contract_rejects_cross_tenant_identifiers() -> None:
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    other_tenant = domain.TenantId("tenant-b")

    with pytest.raises(ValueError, match="request id tenant"):
        _ = domain.ExecutionRequest(
            tenant_id=tenant,
            request_id=domain.RequestId(tenant_id=other_tenant, value="req-1"),
            job_id=domain.JobId(tenant_id=tenant, value="job-1"),
            idempotency_key=domain.IdempotencyKey("key-1"),
            payload={"prompt": "hello"},
        )


@pytest.mark.unit
def test_execution_state_enforces_progression_and_terminal_invariants() -> None:
    domain = _domain_module()
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    started_at = submitted_at + timedelta(seconds=2)
    finished_at = started_at + timedelta(seconds=5)

    queued = domain.ExecutionState(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.QUEUED,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )
    running = queued.transition_to(
        domain.ExecutionStatus.STARTING,
        updated_at=started_at,
        started_at=started_at,
    ).transition_to(
        domain.ExecutionStatus.RUNNING,
        updated_at=started_at,
        timeout_state=domain.TimeoutState.ACTIVE,
    )
    succeeded = running.transition_to(
        domain.ExecutionStatus.SUCCEEDED,
        updated_at=finished_at,
        finished_at=finished_at,
        timeout_state=domain.TimeoutState.CLEARED,
        summary=domain.ResultSummary(output_text="ok", duration_seconds=5.0),
    )

    assert succeeded.status is domain.ExecutionStatus.SUCCEEDED
    assert succeeded.started_at == started_at
    assert succeeded.finished_at == finished_at
    assert succeeded.timeout_state is domain.TimeoutState.CLEARED

    with pytest.raises(ValueError, match="cannot transition"):
        _ = succeeded.transition_to(domain.ExecutionStatus.FAILED)


@pytest.mark.unit
def test_execution_state_requires_timeout_and_cancellation_taxonomy_alignment() -> None:
    domain = _domain_module()
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    started_at = submitted_at + timedelta(seconds=1)
    finished_at = started_at + timedelta(seconds=10)

    timeout_error = domain.TimeoutError("execution exceeded limit").as_details()
    cancelled_error = domain.CancellationError("cancelled by operator").as_details()

    timed_out = domain.ExecutionState(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.TIMED_OUT,
        submitted_at=submitted_at,
        updated_at=finished_at,
        started_at=started_at,
        finished_at=finished_at,
        timeout_state=domain.TimeoutState.EXCEEDED,
        error=timeout_error,
    )
    cancelled = domain.ExecutionState(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.CANCELLED,
        submitted_at=submitted_at,
        updated_at=finished_at,
        finished_at=finished_at,
        cancellation_state=domain.CancellationState.COMPLETED,
        error=cancelled_error,
    )

    assert timed_out.error.category is domain.ErrorCategory.TIMEOUT
    assert cancelled.error.category is domain.ErrorCategory.CANCELLATION

    with pytest.raises(ValueError, match="timeout_state"):
        _ = domain.ExecutionState(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            status=domain.ExecutionStatus.TIMED_OUT,
            submitted_at=submitted_at,
            updated_at=finished_at,
            started_at=started_at,
            finished_at=finished_at,
            timeout_state=domain.TimeoutState.CLEARED,
            error=timeout_error,
        )


@pytest.mark.unit
def test_execution_result_and_error_taxonomy_are_stable() -> None:
    domain = _domain_module()
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    completed_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    gateway_error = domain.GatewayError(
        "temporary upstream outage",
        metadata=(("upstream", "llm-gateway"),),
    ).as_details()

    result = domain.ExecutionResult(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        status=domain.ExecutionStatus.SUCCEEDED,
        completed_at=completed_at,
        payload={"message": "done"},
        summary=domain.ResultSummary(output_text="done", artifact_count=1),
        artifacts=(
            domain.ArtifactSummary(
                key="stdout.txt",
                media_type="text/plain",
                size_bytes=4,
            ),
        ),
    )

    assert result.payload == {"message": "done"}
    assert result.artifacts[0].key == "stdout.txt"
    assert gateway_error.category is domain.ErrorCategory.GATEWAY_FAILURE
    assert gateway_error.retryable is True
    assert gateway_error.code == domain.ErrorCategory.GATEWAY_FAILURE.value

    with pytest.raises(ValueError, match="non-successful results"):
        _ = domain.ExecutionResult(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            status=domain.ExecutionStatus.FAILED,
            completed_at=completed_at,
        )

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from typing import Any

import pytest


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


def _persistence_module() -> Any:
    return importlib.import_module("agentsty_platform.persistence")


def _services_module() -> Any:
    return importlib.import_module("agentsty_platform.services")


def _build_submit_request(tenant: Any, *, key: str, prompt: str) -> Any:
    domain = _domain_module()
    executors = _executors_module()
    gateway = _gateway_module()
    services = _services_module()

    return services.ExecutionSubmitRequest(
        tenant_id=tenant,
        idempotency_key=domain.IdempotencyKey(key),
        gateway_request=gateway.GatewayRequest(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(
                provider="internal-openai",
                model="gpt-4o-mini",
            ),
            messages=(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.USER,
                    content=prompt,
                ),
            ),
            allowlist=gateway.GatewayAllowlist(
                allowed_providers=("internal-openai",),
                allowed_models=("gpt-4o-mini",),
            ),
        ),
        sandbox_program=executors.SandboxProgramSpec(
            command=("python",),
            args=("-m", "agentsty_platform.runner"),
            working_directory="/workspace",
        ),
        sandbox_resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=128,
        ),
    )


def _fixed_request_id_factory(request: Any) -> Any:
    domain = _domain_module()
    return domain.RequestId(request.tenant_id, "req-fixed")


def _fixed_job_id_factory(request: Any) -> Any:
    domain = _domain_module()
    return domain.JobId(request.tenant_id, "job-fixed")


def _replay_request_id_factory(request: Any) -> Any:
    domain = _domain_module()
    return domain.RequestId(request.tenant_id, "req-replay")


def _replay_job_id_factory(request: Any) -> Any:
    domain = _domain_module()
    return domain.JobId(request.tenant_id, "job-replay")


@pytest.mark.unit
def test_request_intake_service_reserves_idempotency_and_binds_trace_context() -> None:
    domain = _domain_module()
    observability = _observability_module()
    persistence = _persistence_module()
    services = _services_module()

    tenant = domain.TenantId("tenant-a")
    request = _build_submit_request(tenant, key="idem-intake", prompt="hello unit")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        metadata=(("origin", "unit-test"),),
    )
    intake_service = services.RequestIntakeService(
        jobs=persistence.InMemoryJobRepository(),
        request_id_factory=_fixed_request_id_factory,
        job_id_factory=_fixed_job_id_factory,
    )

    result = intake_service.intake(
        services.ExecutionSubmitRequest(
            tenant_id=request.tenant_id,
            idempotency_key=request.idempotency_key,
            gateway_request=request.gateway_request,
            sandbox_program=request.sandbox_program,
            sandbox_resources=request.sandbox_resources,
            desired_isolation=request.desired_isolation,
            trace_context=trace_context,
        )
    )

    assert result.idempotent_replay is False
    assert result.execution.request_id.value == "req-fixed"
    assert result.execution.job_id.value == "job-fixed"
    assert result.trace_context.request_id == result.execution.request_id
    assert result.trace_context.job_id == result.execution.job_id
    assert ("service", "request_intake") in result.execution.metadata
    assert ("origin", "unit-test") in result.execution.metadata
    assert (
        intake_service.jobs.find_by_idempotency_key(tenant, request.idempotency_key)
        is not None
    )


@pytest.mark.unit
def test_request_intake_service_replays_existing_idempotent_request() -> None:
    domain = _domain_module()
    persistence = _persistence_module()
    services = _services_module()

    tenant = domain.TenantId("tenant-a")
    request = _build_submit_request(tenant, key="idem-replay", prompt="hello replay")
    jobs = persistence.InMemoryJobRepository()
    intake_service = services.RequestIntakeService(
        jobs=jobs,
        request_id_factory=_replay_request_id_factory,
        job_id_factory=_replay_job_id_factory,
    )

    first = intake_service.intake(request)
    second = intake_service.intake(request)

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.job.request.job_id == first.job.request.job_id
    assert second.execution.request_id == first.execution.request_id
    assert ("idempotent_replay", "true") in second.trace_context.metadata


@pytest.mark.unit
def test_policy_quota_decision_raises_category_specific_shared_errors() -> None:
    domain = _domain_module()
    services = _services_module()

    with pytest.raises(domain.QuotaExceededError, match="quota"):
        services.PolicyQuotaDecision(
            allowed=False,
            error=domain.QuotaExceededError("quota exhausted").as_details(),
        ).require_allowed()

    with pytest.raises(domain.PolicyViolationError, match="blocked"):
        services.PolicyQuotaDecision(
            allowed=False,
            error=domain.PolicyViolationError("blocked by policy").as_details(),
        ).require_allowed()


@pytest.mark.unit
def test_in_memory_policy_quota_service_enforces_submission_and_slot_limits() -> None:
    domain = _domain_module()
    services = _services_module()

    tenant = domain.TenantId("tenant-a")
    blocked_request = _build_submit_request(
        tenant,
        key="idem-policy",
        prompt="blocked prompt",
    )
    policy_service = services.InMemoryPolicyQuotaService(
        max_active_executions_per_tenant=1,
        blocked_models=frozenset({"internal-openai/gpt-4o-mini"}),
    )

    submission_decision = policy_service.evaluate_submission(blocked_request)

    assert submission_decision.allowed is False
    assert submission_decision.error is not None
    assert submission_decision.error.category is domain.ErrorCategory.POLICY_VIOLATION

    allowed_request = _build_submit_request(
        tenant,
        key="idem-quota",
        prompt="allowed prompt",
    )
    quota_service = services.InMemoryPolicyQuotaService(
        max_active_executions_per_tenant=1
    )
    first_slot = quota_service.acquire_execution_slot(
        tenant,
        domain.JobId(tenant, "job-1"),
    )
    second_slot = quota_service.acquire_execution_slot(
        tenant,
        domain.JobId(tenant, "job-2"),
    )
    quota_service.release_execution_slot(tenant, domain.JobId(tenant, "job-1"))
    third_slot = quota_service.acquire_execution_slot(
        tenant,
        domain.JobId(tenant, "job-3"),
    )
    submission_allowed = quota_service.evaluate_submission(allowed_request)

    assert first_slot.allowed is True
    assert second_slot.allowed is False
    assert second_slot.error is not None
    assert second_slot.error.category is domain.ErrorCategory.QUOTA_EXCEEDED
    assert third_slot.allowed is True
    assert submission_allowed.allowed is True


@pytest.mark.unit
def test_serialization_contracts_preserve_error_and_metadata_fields() -> None:
    domain = _domain_module()
    persistence = _persistence_module()

    tenant = domain.TenantId("tenant-a")
    job_id = domain.JobId(tenant, "job-serialize")
    error = domain.GatewayError(
        "temporary gateway outage",
        metadata=(("upstream", "gateway"),),
    ).as_details()
    artifact_record = persistence.ArtifactMetadataRecord(
        tenant_id=tenant,
        job_id=job_id,
        artifact=domain.ArtifactSummary(
            key="logs/stdout.txt",
            media_type="text/plain",
            size_bytes=4,
            metadata=(("redaction", "none"),),
        ),
        content_ref=persistence.ArtifactContentRef(
            storage_backend="local_fs",
            locator="tenant-a/job-serialize/logs/stdout.txt",
        ),
    )

    serialized_error = json.loads(json.dumps(asdict(error), default=str))
    serialized_artifact = json.loads(json.dumps(asdict(artifact_record), default=str))

    assert serialized_error["category"] == "gateway_failure"
    assert serialized_error["metadata"] == [["upstream", "gateway"]]
    assert serialized_artifact["tenant_id"]["value"] == "tenant-a"
    assert serialized_artifact["artifact"]["metadata"] == [["redaction", "none"]]
    assert serialized_artifact["content_ref"]["storage_backend"] == "local_fs"

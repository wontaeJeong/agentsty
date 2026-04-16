from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .support import (
    api_package,
    build_gateway_failure_api_dependencies,
    build_local_api_dependencies,
    build_running_api_dependencies,
    build_sandbox_failure_api_dependencies,
    build_timeout_api_dependencies,
    request_payload,
)

pytestmark = pytest.mark.e2e


def _advance_deferred_job_to_succeeded(
    dependencies: Any, *, tenant_id: str, job_id: str
) -> None:
    from .support import domain_module, gateway_module

    domain = domain_module()
    gateway = gateway_module()
    tenant = domain.TenantId(tenant_id)
    job = domain.JobId(tenant_id=tenant, value=job_id)
    record = dependencies.orchestrator.jobs.get(tenant, job)
    runtime_adapter = dependencies.orchestrator.runtime_adapter
    prompt = record.request.payload.messages[0].content
    runtime_adapter._sessions[f"deferred-{job_id}"]["result"] = domain.ExecutionResult(
        tenant_id=record.tenant_id,
        request_id=record.request.request_id,
        job_id=record.request.job_id,
        status=domain.ExecutionStatus.SUCCEEDED,
        completed_at=(record.state.started_at or record.request.submitted_at)
        + timedelta(seconds=1),
        payload=gateway.GatewayResponse(
            tenant_id=record.tenant_id,
            target=record.request.payload.target,
            message=gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.ASSISTANT,
                content=f"deferred gateway echo: {prompt}",
            ),
            finish_reason=gateway.GatewayFinishReason.STOP,
            usage=gateway.GatewayUsage(input_tokens=1, output_tokens=1),
        ),
        summary=domain.ResultSummary(duration_seconds=0.0),
    )


def test_happy_path_executes_through_public_api_and_full_local_stack(
    tmp_path: Path,
) -> None:
    app = api_package().create_app(build_local_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-happy",
            prompt="hello end to end",
            idempotency_key="idem-happy",
            request_id="req-happy",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["tenant_id"] == "tenant-happy"
    assert payload["request_id"] == "req-happy"
    assert payload["cleanup_performed"] is True
    assert payload["choices"][0]["message"]["content"] == (
        "local gateway echo: hello end to end"
    )
    assert payload["usage"]["total_tokens"] > 0


def test_quota_rejection_is_reported_at_the_public_api_boundary(
    tmp_path: Path,
) -> None:
    app = api_package().create_app(
        build_running_api_dependencies(tmp_path, quota_limit=1)
    )
    client = TestClient(app)

    first = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-quota",
            prompt="hold the first slot",
            idempotency_key="idem-quota-1",
        ),
    )
    second = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-quota",
            prompt="need another slot",
            idempotency_key="idem-quota-2",
        ),
    )

    assert first.status_code == 202
    assert first.json()["status"] == "running"
    assert second.status_code == 429
    assert second.json()["error"]["category"] == "quota_exceeded"
    assert "no remaining execution quota" in second.json()["error"]["message"]


def test_sandbox_failure_surfaces_as_a_terminal_api_error(tmp_path: Path) -> None:
    app = api_package().create_app(build_sandbox_failure_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-sandbox",
            prompt="trigger sandbox creation failure",
            idempotency_key="idem-sandbox",
        ),
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["category"] == "sandbox_creation_failure"
    assert "sandbox creation failed" in payload["error"]["message"]


def test_gateway_failure_surfaces_as_a_gateway_api_error(tmp_path: Path) -> None:
    app = api_package().create_app(build_gateway_failure_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-gateway",
            prompt="trigger gateway outage",
            idempotency_key="idem-gateway",
        ),
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["category"] == "gateway_failure"
    assert payload["error"]["retryable"] is True
    assert payload["error"]["metadata"]["failure_kind"] == "unavailable"


def test_timeout_surfaces_as_gateway_style_terminal_timeout_response(
    tmp_path: Path,
) -> None:
    app = api_package().create_app(build_timeout_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-timeout",
            prompt="run until timeout",
            idempotency_key="idem-timeout",
        ),
    )

    assert response.status_code == 504
    payload = response.json()
    assert payload["error"]["category"] == "timeout"
    assert payload["job_id"]


def test_cancellation_completes_through_submit_status_and_cancel_routes(
    tmp_path: Path,
) -> None:
    dependencies = build_running_api_dependencies(tmp_path, quota_limit=1)
    app = api_package().create_app(dependencies)
    client = TestClient(app)

    submit = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-cancel",
            prompt="hold for cancellation",
            idempotency_key="idem-cancel",
        ),
    )
    job_id = submit.json()["job_id"]

    _advance_deferred_job_to_succeeded(
        dependencies, tenant_id="tenant-cancel", job_id=job_id
    )

    status_response = client.get(
        f"/v1/chat/completions/{job_id}",
        headers={"X-Agentsty-Tenant-Id": "tenant-cancel"},
    )
    cancel_submit = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-cancel",
            prompt="hold for cancellation",
            idempotency_key="idem-cancel-2",
        ),
    )
    cancel_job_id = cancel_submit.json()["job_id"]
    cancel = client.post(
        f"/v1/chat/completions/{cancel_job_id}/cancel",
        headers={
            "X-Agentsty-Tenant-Id": "tenant-cancel",
            "X-Agentsty-Cancel-Reason": "operator cancelled",
        },
    )

    assert submit.status_code == 202
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["choices"][0]["message"]["content"].startswith(
        "deferred gateway echo:"
    )
    assert cancel.status_code == 202
    cancel_payload = cancel.json()
    assert cancel_payload["status"] == "cancelled"
    assert cancel_payload["cancellation_requested"] is True
    assert cancel_payload["cleanup_performed"] is True


def test_multi_tenant_isolation_keeps_idempotency_and_jobs_tenant_scoped(
    tmp_path: Path,
) -> None:
    app = api_package().create_app(build_local_api_dependencies(tmp_path))
    client = TestClient(app)

    tenant_a_first = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-a",
            prompt="same key first tenant",
            idempotency_key="shared-idem",
            request_id="req-shared",
        ),
    )
    tenant_a_replay = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-a",
            prompt="same key first tenant",
            idempotency_key="shared-idem",
            request_id="req-shared",
        ),
    )
    tenant_b = client.post(
        "/v1/chat/completions",
        json=request_payload(
            "tenant-b",
            prompt="same key second tenant",
            idempotency_key="shared-idem",
            request_id="req-shared",
        ),
    )

    assert tenant_a_first.status_code == 200
    assert tenant_a_replay.status_code == 200
    assert tenant_b.status_code == 200
    tenant_a_first_payload = tenant_a_first.json()
    tenant_a_replay_payload = tenant_a_replay.json()
    tenant_b_payload = tenant_b.json()
    assert tenant_a_first_payload["job_id"] == tenant_a_replay_payload["job_id"]
    assert tenant_a_replay_payload["idempotent_replay"] is True
    assert tenant_b_payload["job_id"] != tenant_a_first_payload["job_id"]
    assert tenant_b_payload["idempotent_replay"] is False
    assert tenant_b_payload["tenant_id"] == "tenant-b"

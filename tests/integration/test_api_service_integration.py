from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .support import (
    api_package,
    build_deferred_api_dependencies,
    build_local_api_dependencies,
)

pytestmark = pytest.mark.integration


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


def test_chat_completions_api_executes_through_shared_service_stack(
    tmp_path: Path,
) -> None:
    app = api_package().create_app(build_local_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "request_id": "req-api-1",
            "idempotency_key": "idem-api-1",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello api"}],
            "request_timeout_seconds": 30,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["request_id"] == "req-api-1"
    assert payload["choices"][0]["message"]["content"].startswith(
        "local gateway echo: hello api"
    )
    assert payload["usage"]["total_tokens"] > 0


def test_status_and_cancellation_routes_cover_running_integration_flow(
    tmp_path: Path,
) -> None:
    dependencies = build_deferred_api_dependencies(tmp_path)
    app = api_package().create_app(dependencies)
    client = TestClient(app)

    submit = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-running",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold"}],
        },
    )

    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    _advance_deferred_job_to_succeeded(
        dependencies, tenant_id="tenant-a", job_id=job_id
    )

    status_response = client.get(
        f"/v1/chat/completions/{job_id}",
        headers={"X-Agentsty-Tenant-Id": "tenant-a"},
    )
    cancel_submit = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-cancel",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold"}],
        },
    )
    cancel_job_id = cancel_submit.json()["job_id"]
    cancel_response = client.post(
        f"/v1/chat/completions/{cancel_job_id}/cancel",
        headers={
            "X-Agentsty-Tenant-Id": "tenant-a",
            "X-Agentsty-Cancel-Reason": "operator stop",
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["choices"][0]["message"]["content"].startswith(
        "deferred gateway echo:"
    )
    assert cancel_response.status_code == 202
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["cancellation_requested"] is True

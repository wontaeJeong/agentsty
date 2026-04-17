from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from agentsty.application.errors import ApplicationExecutionError
from agentsty.domain.execution import ExecutionRequest
from agentsty.interfaces.http.dependencies import get_execution_service
from apps.api.main import create_app


class FailingExecutionService:
    def execute(self, request: ExecutionRequest) -> NoReturn:
        del request
        raise ApplicationExecutionError("Execution failed: forced failure", status_code=502)


def test_chat_completions_happy_path() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-demo",
            "message": "hello phase1",
            "metadata": {"trace_id": "demo-1"},
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["generated_text"] == "OpenCodeRuntime stub response: hello phase1"
    assert body["runtime_name"] == "opencode"
    assert body["sandbox_execution_id"].startswith("sbx-")
    assert isinstance(body["artifacts"], list)


def test_chat_completions_validation_failure() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/chat/completions", json={})

    assert response.status_code == 422


def test_chat_completions_execution_failure() -> None:
    app = create_app()
    app.dependency_overrides[get_execution_service] = FailingExecutionService
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"tenant_id": "tenant-demo", "message": "hello phase1", "metadata": {}},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "Execution failed: forced failure"}


def test_invalid_runtime_fails_app_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSTY_DEFAULT_RUNTIME", "bad")

    with pytest.raises(ValueError, match="Unsupported runtime: bad"):
        create_app()


def test_invalid_sandbox_fails_app_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTSTY_SANDBOX_MODE", "bad")

    with pytest.raises(ValueError, match="Unsupported sandbox mode: bad"):
        create_app()

import pytest
from pydantic import ValidationError

from agentsty.interfaces.http.schemas import ChatCompletionRequest, ChatCompletionResponse


def test_chat_completion_request_accepts_minimal_payload() -> None:
    payload = ChatCompletionRequest(tenant_id="tenant-a", message="hello", metadata={"trace": "1"})

    assert payload.tenant_id == "tenant-a"
    assert payload.message == "hello"


def test_chat_completion_request_rejects_empty_fields() -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest(tenant_id="", message="")


def test_chat_completion_response_contains_required_fields() -> None:
    response = ChatCompletionResponse(
        request_id="req-1",
        status="completed",
        generated_text="hi",
        artifacts=[],
        runtime_name="opencode",
        sandbox_execution_id="sbx-1",
    )

    assert response.runtime_name == "opencode"
    assert response.sandbox_execution_id == "sbx-1"

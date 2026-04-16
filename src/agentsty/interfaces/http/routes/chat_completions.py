from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from agentsty.application.errors import ApplicationExecutionError
from agentsty.application.services.execution_service import ExecutionService
from agentsty.domain.execution import ExecutionRequest, TenantId
from agentsty.infrastructure.config.settings import Settings, get_settings
from agentsty.interfaces.http.dependencies import get_execution_service
from agentsty.interfaces.http.schemas import (
    ArtifactResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
)

router = APIRouter(prefix="/v1/chat/completions", tags=["chat-completions"])


@router.post("", response_model=ChatCompletionResponse)
def create_chat_completion(
    payload: ChatCompletionRequest,
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatCompletionResponse:
    request = ExecutionRequest(
        request_id=str(uuid4()),
        tenant_id=TenantId(payload.tenant_id),
        message=payload.message,
        metadata=payload.metadata,
        timeout_seconds=settings.default_timeout_seconds,
    )

    try:
        result = execution_service.execute(request)
    except ApplicationExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ChatCompletionResponse(
        request_id=result.request_id,
        status=result.status,
        generated_text=result.generated_text,
        artifacts=[ArtifactResponse(**artifact.__dict__) for artifact in result.artifacts],
        runtime_name=result.runtime_name,
        sandbox_execution_id=result.sandbox_execution_id,
    )

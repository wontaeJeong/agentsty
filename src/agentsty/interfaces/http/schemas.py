from typing import Any

from pydantic import BaseModel, Field


class ChatCompletionRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None


class ArtifactResponse(BaseModel):
    name: str
    mime_type: str
    uri: str | None = None
    content: str | None = None


class ChatCompletionResponse(BaseModel):
    request_id: str
    status: str
    generated_text: str
    artifacts: list[ArtifactResponse]
    runtime_name: str
    sandbox_execution_id: str


class HealthResponse(BaseModel):
    status: str

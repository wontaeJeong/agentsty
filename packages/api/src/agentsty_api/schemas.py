"""Transport-specific request and response schemas for the FastAPI surface."""

# pyright: reportMissingImports=false

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatCompletionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    model: str
    messages: list[ChatCompletionMessage]
    tenant_id: str
    provider: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = Field(default=None, alias="max_tokens")
    stop: list[str] = Field(default_factory=list)
    request_timeout_seconds: int | None = None
    execution_timeout_seconds: int | None = None
    cancellation_grace_period_seconds: int | None = None


class ChatCompletionChoiceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    name: str | None = None


class ChatCompletionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    message: ChatCompletionChoiceMessage
    finish_reason: str | None = None


class UsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ErrorResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    category: str
    code: str
    retryable: bool
    metadata: dict[str, str] = Field(default_factory=dict)


class ExecutionSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_text: str | None = None
    duration_seconds: float | None = None
    artifact_count: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)


class ArtifactContentRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_backend: str
    locator: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    media_type: str | None = None
    size_bytes: int = 0
    sha256: str | None = None
    redacted: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    storage: ArtifactContentRefResponse | None = None


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    tenant_id: str
    request_id: str
    job_id: str
    status: str
    idempotent_replay: bool = False
    cleanup_performed: bool = False
    choices: list[ChatCompletionChoice] = Field(default_factory=list)
    usage: UsageResponse | None = None
    summary: ExecutionSummaryResponse | None = None
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    error: ErrorResponseBody | None = None


class CancellationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    request_id: str
    job_id: str
    status: str
    cancellation_requested: bool
    cleanup_performed: bool = False
    error: ErrorResponseBody | None = None


class HealthComponentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    detail: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str
    status: str
    checked_at: str
    summary: str | None = None
    components: list[HealthComponentResponse] = Field(default_factory=list)


class ReadinessCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ready: bool
    requirement: str
    detail: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str
    ready: bool
    checked_at: str
    summary: str | None = None
    blocking_checks: list[str] = Field(default_factory=list)
    checks: list[ReadinessCheckResponse] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorResponseBody
    tenant_id: str | None = None
    request_id: str | None = None
    job_id: str | None = None

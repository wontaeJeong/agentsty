"""Runtime-agnostic request and response contracts for the internal LLM gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..domain.errors import PolicyViolationError
from ..domain.ids import IdempotencyKey, TenantId
from ..domain.models import Metadata, normalize_metadata
from ..observability.tracing import TraceContext


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_optional(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} must not be blank")
    return cleaned


class GatewayMessageRole(StrEnum):
    """Stable conversational roles understood by the internal gateway."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class GatewayMessage:
    """Provider-neutral chat message sent to or returned from the gateway."""

    role: GatewayMessageRole
    content: str
    name: str | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_content = self.content.strip()
        if not clean_content:
            raise ValueError("gateway message content must not be empty")
        object.__setattr__(self, "content", clean_content)
        object.__setattr__(self, "name", _normalize_optional("message name", self.name))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class GatewayModelTarget:
    """Gateway-routed model selection without exposing vendor client ownership."""

    model: str
    provider: str | None = None

    def __post_init__(self) -> None:
        clean_model = self.model.strip()
        if not clean_model:
            raise ValueError("gateway target model must not be empty")
        object.__setattr__(self, "model", clean_model)
        object.__setattr__(
            self, "provider", _normalize_optional("provider", self.provider)
        )

    @property
    def label(self) -> str:
        if self.provider is None:
            return self.model
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True, slots=True)
class GatewayAllowlist:
    """Gateway-layer allowlist for model-routing policy enforcement."""

    allowed_providers: tuple[str, ...] = ()
    allowed_models: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_providers",
            tuple(item.strip() for item in self.allowed_providers if item.strip()),
        )
        object.__setattr__(
            self,
            "allowed_models",
            tuple(item.strip() for item in self.allowed_models if item.strip()),
        )

    def allows(self, target: GatewayModelTarget) -> bool:
        provider_allowed = (
            True
            if not self.allowed_providers
            else target.provider is not None
            and target.provider in self.allowed_providers
        )
        model_allowed = (
            True if not self.allowed_models else target.model in self.allowed_models
        )
        return provider_allowed and model_allowed

    def require_allowed(self, target: GatewayModelTarget) -> None:
        if self.allows(target):
            return
        details: list[tuple[str, str]] = [("target", target.label)]
        if self.allowed_providers:
            details.append(("allowed_providers", ",".join(self.allowed_providers)))
        if self.allowed_models:
            details.append(("allowed_models", ",".join(self.allowed_models)))
        raise PolicyViolationError(
            "gateway request target is not allowed by policy",
            metadata=tuple(details),
        )


@dataclass(frozen=True, slots=True)
class GatewaySampling:
    """Sampling and output controls for generation requests."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")
        object.__setattr__(
            self,
            "stop_sequences",
            tuple(
                item
                for item in (value.strip() for value in self.stop_sequences)
                if item
            ),
        )


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """Internal gateway invocation contract for later service and runtime layers."""

    tenant_id: TenantId
    target: GatewayModelTarget
    messages: tuple[GatewayMessage, ...]
    allowlist: GatewayAllowlist = field(default_factory=GatewayAllowlist)
    sampling: GatewaySampling = field(default_factory=GatewaySampling)
    idempotency_key: IdempotencyKey | None = None
    request_timeout_seconds: int | None = None
    trace_context: TraceContext | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("gateway request must include at least one message")
        if (
            self.request_timeout_seconds is not None
            and self.request_timeout_seconds < 1
        ):
            raise ValueError("request timeout must be at least 1 second")
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError(
                    "trace context tenant must match gateway request tenant"
                )
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))
        self.allowlist.require_allowed(self.target)


class GatewayFinishReason(StrEnum):
    """Stable gateway completion reasons exposed to downstream orchestration."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class GatewayUsage:
    """Provider-neutral token accounting for gateway responses."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise ValueError("input_tokens must not be negative")
        if self.output_tokens < 0:
            raise ValueError("output_tokens must not be negative")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    """Gateway response contract that stays transport- and vendor-agnostic."""

    tenant_id: TenantId
    target: GatewayModelTarget
    message: GatewayMessage
    finish_reason: GatewayFinishReason = GatewayFinishReason.STOP
    usage: GatewayUsage = field(default_factory=GatewayUsage)
    gateway_request_id: str | None = None
    trace_context: TraceContext | None = None
    completed_at: datetime = field(default_factory=_utc_now)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "gateway_request_id",
            _normalize_optional("gateway_request_id", self.gateway_request_id),
        )
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError(
                    "trace context tenant must match gateway response tenant"
                )
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

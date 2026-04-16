"""Baseline local/test implementation for the internal gateway abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import override

from .auth import InternalAuthContext
from .client import GatewayEndpoint, GatewayTransport
from .contracts import (
    GatewayFinishReason,
    GatewayMessage,
    GatewayMessageRole,
    GatewayRequest,
    GatewayResponse,
    GatewayUsage,
)
from .errors import GatewayFailure


@dataclass(frozen=True, slots=True)
class CapturedGatewayCall:
    """Recorded local call details for tests and local orchestration inspection."""

    endpoint: GatewayEndpoint
    request: GatewayRequest
    auth_context: InternalAuthContext


@dataclass(slots=True)
class LocalGatewayTransport(GatewayTransport):
    """In-memory gateway backend with scripted outcomes and deterministic fallback."""

    scripted_outcomes: list[GatewayResponse | GatewayFailure] = field(
        default_factory=list
    )
    captured_calls: list[CapturedGatewayCall] = field(default_factory=list)
    default_response_prefix: str = "local gateway echo: "

    @override
    def send(
        self,
        endpoint: GatewayEndpoint,
        request: GatewayRequest,
        *,
        auth_context: InternalAuthContext,
    ) -> GatewayResponse:
        self.captured_calls.append(
            CapturedGatewayCall(
                endpoint=endpoint,
                request=request,
                auth_context=auth_context,
            )
        )
        if self.scripted_outcomes:
            outcome = self.scripted_outcomes.pop(0)
            if isinstance(outcome, GatewayFailure):
                raise outcome
            return outcome

        prompt_text = _last_prompt_text(request)
        output_text = f"{self.default_response_prefix}{prompt_text}"
        return GatewayResponse(
            tenant_id=request.tenant_id,
            target=request.target,
            message=GatewayMessage(
                role=GatewayMessageRole.ASSISTANT,
                content=output_text,
            ),
            finish_reason=GatewayFinishReason.STOP,
            usage=GatewayUsage(
                input_tokens=_estimate_tokens(prompt_text),
                output_tokens=_estimate_tokens(output_text),
            ),
            trace_context=request.trace_context,
            metadata=request.metadata,
        )


def _last_prompt_text(request: GatewayRequest) -> str:
    for message in reversed(request.messages):
        if message.role in {GatewayMessageRole.USER, GatewayMessageRole.SYSTEM}:
            return message.content
    return request.messages[-1].content


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))

"""Production-oriented non-local gateway transport and auth wrappers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, cast, override
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..domain.ids import TenantId
from ..observability.tracing import TraceContext
from .auth import (
    InternalAuthContext,
    InternalAuthToken,
    StaticInternalAuthTokenProvider,
)
from .client import GatewayEndpoint, GatewayTransport
from .contracts import (
    GatewayFinishReason,
    GatewayMessage,
    GatewayMessageRole,
    GatewayRequest,
    GatewayResponse,
    GatewayUsage,
)
from .errors import GatewayFailure, GatewayFailureKind, gateway_failure_from_status


class _AuthSettingsLike(Protocol):
    issuer: str | None


class _SettingsLike(Protocol):
    auth: _AuthSettingsLike


class _HTTPResponseLike(Protocol):
    def __enter__(self) -> _HTTPResponseLike: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...

    def read(self) -> bytes: ...


@dataclass(slots=True)
class ServiceGatewayTokenProvider:
    """Non-local service token issuer used by default gateway composition."""

    issuer: str
    subject_prefix: str = "agentsty-service"
    ttl_seconds: int = 300
    _delegate: StaticInternalAuthTokenProvider = field(init=False)

    def __post_init__(self) -> None:
        self.issuer = self.issuer.strip()
        if not self.issuer:
            raise ValueError("issuer must not be empty")
        self._delegate = StaticInternalAuthTokenProvider(
            issuer=self.issuer,
            subject_prefix=self.subject_prefix,
            ttl_seconds=self.ttl_seconds,
        )

    @classmethod
    def from_settings(cls, settings: _SettingsLike) -> ServiceGatewayTokenProvider:
        auth_settings = settings.auth
        issuer = auth_settings.issuer or "agentsty-internal"
        return cls(issuer=issuer)

    def issue_token(
        self,
        *,
        tenant_id: TenantId,
        audience: str,
        trace_context: TraceContext | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> InternalAuthToken:
        return self._delegate.issue_token(
            tenant_id=tenant_id,
            audience=audience,
            trace_context=trace_context,
            metadata=metadata + (("auth_mode", "service_gateway_token"),),
        )


@dataclass(slots=True)
class HTTPGatewayTransport(GatewayTransport):
    """HTTP transport used by non-local profiles for internal gateway access."""

    timeout_seconds: float = 30.0
    user_agent: str = "agentsty-gateway/0.0.0"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

    @override
    def send(
        self,
        endpoint: GatewayEndpoint,
        request: GatewayRequest,
        *,
        auth_context: InternalAuthContext,
    ) -> GatewayResponse:
        payload = json.dumps(_request_payload(request)).encode("utf-8")
        http_request = urllib_request.Request(
            endpoint.url,
            data=payload,
            headers=_headers(auth_context, user_agent=self.user_agent),
            method="POST",
        )

        try:
            response_handle = cast(
                _HTTPResponseLike,
                urllib_request.urlopen(
                    http_request,
                    timeout=self.timeout_seconds,
                ),
            )
            with response_handle as response:
                body = response.read().decode("utf-8")
                decoded_payload = cast(object, json.loads(body))
                parsed = _as_payload(decoded_payload)
        except urllib_error.HTTPError as error:
            raise gateway_failure_from_status(
                error.code,
                _error_message(error),
                metadata=(("transport", "http_gateway"),),
            ) from error
        except urllib_error.URLError as error:
            raise GatewayFailure(
                GatewayFailureKind.TRANSPORT,
                str(error.reason),
                metadata=(("transport", "http_gateway"),),
            ) from error
        except TimeoutError as error:
            raise GatewayFailure(
                GatewayFailureKind.TIMEOUT,
                str(error),
                metadata=(("transport", "http_gateway"),),
            ) from error

        return _response_from_payload(request, parsed)


def _headers(auth_context: InternalAuthContext, *, user_agent: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "X-Agentsty-Tenant": auth_context.tenant_id.value,
    }
    authorization_header = auth_context.authorization_header
    if authorization_header is not None:
        headers["Authorization"] = authorization_header
    return headers


def _request_payload(request: GatewayRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": request.target.model,
        "messages": [
            {
                "role": message.role.value,
                "content": message.content,
                "name": message.name,
            }
            for message in request.messages
        ],
        "metadata": dict(request.metadata),
    }
    if request.target.provider is not None:
        payload["provider"] = request.target.provider
    if request.request_timeout_seconds is not None:
        payload["timeout_seconds"] = request.request_timeout_seconds
    if request.sampling.temperature is not None:
        payload["temperature"] = request.sampling.temperature
    if request.sampling.max_output_tokens is not None:
        payload["max_output_tokens"] = request.sampling.max_output_tokens
    if request.sampling.stop_sequences:
        payload["stop"] = list(request.sampling.stop_sequences)
    if request.idempotency_key is not None:
        payload["idempotency_key"] = request.idempotency_key.value
    return payload


def _as_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GatewayFailure(
            GatewayFailureKind.BAD_REQUEST,
            "gateway returned a non-object response",
            retryable=False,
        )
    normalized: dict[str, object] = {}
    for key, value in cast(dict[object, object], payload).items():
        if isinstance(key, str):
            normalized[key] = value
    return normalized


def _payload_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    payload: dict[str, object] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str):
            payload[key] = item
    return payload


def _first_list_item(values: list[object]) -> object | None:
    if not values:
        return None
    return values[0]


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


def _response_from_payload(
    request: GatewayRequest, payload: dict[str, object]
) -> GatewayResponse:
    content, role_name = _extract_message(payload)
    usage = _extract_usage(payload)
    finish_reason = _extract_finish_reason(payload)
    return GatewayResponse(
        tenant_id=request.tenant_id,
        target=request.target,
        message=GatewayMessage(
            role=GatewayMessageRole(role_name),
            content=content,
        ),
        finish_reason=finish_reason,
        usage=usage,
        gateway_request_id=_optional_string(payload.get("id")),
        trace_context=request.trace_context,
        completed_at=datetime.now(UTC),
        metadata=request.metadata,
    )


def _extract_message(payload: dict[str, object]) -> tuple[str, str]:
    message_payload = _payload_dict(payload.get("message"))
    if message_payload is not None:
        content = str(message_payload.get("content", "")).strip()
        role_name = str(message_payload.get("role", GatewayMessageRole.ASSISTANT.value))
        if content:
            return content, role_name

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GatewayFailure(
            GatewayFailureKind.BAD_REQUEST,
            "gateway response did not include a completion message",
            retryable=False,
        )
    first_choice = _payload_dict(_first_list_item(cast(list[object], choices)))
    if first_choice is None:
        raise GatewayFailure(
            GatewayFailureKind.BAD_REQUEST,
            "gateway response choice was not an object",
            retryable=False,
        )
    nested_message = _payload_dict(first_choice.get("message"))
    if nested_message is None:
        raise GatewayFailure(
            GatewayFailureKind.BAD_REQUEST,
            "gateway response choice did not include a message",
            retryable=False,
        )
    content = str(nested_message.get("content", "")).strip()
    if not content:
        raise GatewayFailure(
            GatewayFailureKind.BAD_REQUEST,
            "gateway response content must not be empty",
            retryable=False,
        )
    role_name = str(nested_message.get("role", GatewayMessageRole.ASSISTANT.value))
    return content, role_name


def _extract_usage(payload: dict[str, object]) -> GatewayUsage:
    usage_payload = _payload_dict(payload.get("usage"))
    if usage_payload is None:
        return GatewayUsage()
    return GatewayUsage(
        input_tokens=_int_value(usage_payload.get("prompt_tokens", 0)),
        output_tokens=_int_value(usage_payload.get("completion_tokens", 0)),
    )


def _extract_finish_reason(payload: dict[str, object]) -> GatewayFinishReason:
    finish_value = payload.get("finish_reason")
    if isinstance(finish_value, str):
        try:
            return GatewayFinishReason(finish_value)
        except ValueError:
            return GatewayFinishReason.ERROR
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = _payload_dict(_first_list_item(cast(list[object], choices)))
        choice_finish = (
            None if first_choice is None else first_choice.get("finish_reason")
        )
        if isinstance(choice_finish, str):
            try:
                return GatewayFinishReason(choice_finish)
            except ValueError:
                return GatewayFinishReason.ERROR
    return GatewayFinishReason.STOP


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None


def _error_message(error: urllib_error.HTTPError) -> str:
    body = error.read().decode("utf-8", errors="ignore").strip()
    if body:
        return body
    return str(error.reason)

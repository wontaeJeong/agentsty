"""Internal gateway client abstraction and config-backed request flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config.settings import PlatformSettings
from ..domain.errors import DomainError
from ..domain.models import Metadata, normalize_metadata
from ..observability.tracing import TraceContext
from .auth import (
    InternalAuthContext,
    InternalAuthTokenProvider,
    resolve_internal_auth_context,
)
from .contracts import GatewayRequest, GatewayResponse
from .errors import GatewayFailure, map_gateway_failure


@dataclass(frozen=True, slots=True)
class GatewayEndpoint:
    """Resolved internal gateway endpoint derived from shared platform config."""

    base_url: str
    request_path: str
    audience: str
    internal_only: bool = True
    require_tls: bool = False

    def __post_init__(self) -> None:
        clean_base_url = self.base_url.rstrip("/")
        if not clean_base_url:
            raise ValueError("base_url must not be empty")
        if not self.request_path.startswith("/"):
            raise ValueError("request_path must start with '/'")
        if not self.audience.strip():
            raise ValueError("audience must not be empty")
        if not self.internal_only:
            raise ValueError("gateway endpoint must remain internal-only")
        if self.require_tls and not clean_base_url.startswith("https://"):
            raise ValueError("gateway endpoint must use https when TLS is required")
        object.__setattr__(self, "base_url", clean_base_url)

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.request_path}"

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> GatewayEndpoint:
        return cls(
            base_url=settings.gateway.base_url,
            request_path=settings.gateway.request_path,
            audience=settings.gateway.audience,
            internal_only=settings.gateway.internal_only,
            require_tls=settings.gateway.require_tls,
        )


class GatewayTransport(Protocol):
    """Transport/backend seam behind the shared internal gateway client."""

    def send(
        self,
        endpoint: GatewayEndpoint,
        request: GatewayRequest,
        *,
        auth_context: InternalAuthContext,
    ) -> GatewayResponse: ...


class GatewayClient(Protocol):
    """Shared client interface consumed by later platform layers."""

    def generate(self, request: GatewayRequest) -> GatewayResponse: ...


@dataclass(slots=True)
class InternalGatewayClient:
    """Shared client used by platform layers instead of vendor APIs directly."""

    settings: PlatformSettings
    transport: GatewayTransport
    token_provider: InternalAuthTokenProvider | None = None
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    @property
    def endpoint(self) -> GatewayEndpoint:
        return GatewayEndpoint.from_settings(self.settings)

    def generate(self, request: GatewayRequest) -> GatewayResponse:
        """Execute a provider-neutral generation request through the internal gateway."""

        endpoint = self.endpoint
        auth_context = resolve_internal_auth_context(
            tenant_id=request.tenant_id,
            audience=endpoint.audience,
            token_provider=self.token_provider,
            trace_context=request.trace_context,
            allow_anonymous=(
                not self.settings.auth.required
                and self.settings.auth.allow_anonymous_local
            ),
            metadata=_request_metadata(request),
        )

        attempt = 0
        while True:
            attempt += 1
            try:
                return self.transport.send(
                    endpoint,
                    request,
                    auth_context=auth_context,
                )
            except GatewayFailure as error:
                mapped = map_gateway_failure(error)
            except DomainError as error:
                mapped = error
            except (
                Exception
            ) as error:  # pragma: no cover - defensive normalization path
                mapped = map_gateway_failure(error)

            if mapped.details.retryable and attempt < self.max_attempts:
                continue
            raise mapped


def _request_metadata(request: GatewayRequest) -> Metadata:
    metadata: Metadata = (
        ("target", request.target.label),
        ("message_count", str(len(request.messages))),
    )
    if request.trace_context is not None:
        trace_context: TraceContext = request.trace_context
        metadata = metadata + normalize_metadata(trace_context.to_metadata())
    return metadata + request.metadata

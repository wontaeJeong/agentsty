"""Gateway-specific failure inputs and mapping into the shared domain taxonomy."""

from __future__ import annotations

from enum import StrEnum

from ..domain.errors import (
    AuthenticationError,
    AuthorizationError,
    DomainError,
    GatewayError,
    InvalidRequestError,
    QuotaExceededError,
    TimeoutError,
)
from ..domain.models import Metadata, normalize_metadata


class GatewayFailureKind(StrEnum):
    """Normalized gateway failure kinds independent of any transport backend."""

    BAD_REQUEST = "bad_request"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    UNKNOWN = "unknown"

    @property
    def default_retryable(self) -> bool:
        return self in {
            self.RATE_LIMITED,
            self.TIMEOUT,
            self.UNAVAILABLE,
            self.TRANSPORT,
        }


class GatewayFailure(Exception):
    """Gateway backend failure information before domain mapping occurs."""

    kind: GatewayFailureKind
    retryable: bool
    status_code: int | None
    metadata: Metadata

    def __init__(
        self,
        kind: GatewayFailureKind,
        message: str,
        *,
        retryable: bool | None = None,
        status_code: int | None = None,
        metadata: Metadata = (),
    ) -> None:
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("gateway failure message must not be empty")
        if status_code is not None and status_code < 100:
            raise ValueError("status_code must be a valid HTTP-like status code")
        super().__init__(clean_message)
        self.kind = kind
        self.retryable = kind.default_retryable if retryable is None else retryable
        self.status_code = status_code
        self.metadata = normalize_metadata(metadata)


def gateway_failure_from_status(
    status_code: int,
    message: str,
    *,
    metadata: Metadata = (),
) -> GatewayFailure:
    """Translate a status-code-like outcome into a normalized gateway failure."""

    if status_code in {400, 404, 409, 422}:
        kind = GatewayFailureKind.BAD_REQUEST
    elif status_code == 401:
        kind = GatewayFailureKind.UNAUTHENTICATED
    elif status_code == 403:
        kind = GatewayFailureKind.FORBIDDEN
    elif status_code == 429:
        kind = GatewayFailureKind.RATE_LIMITED
    elif status_code in {408, 504}:
        kind = GatewayFailureKind.TIMEOUT
    elif status_code in {502, 503}:
        kind = GatewayFailureKind.UNAVAILABLE
    else:
        kind = GatewayFailureKind.UNKNOWN
    status_metadata = normalize_metadata(metadata) + (
        ("status_code", str(status_code)),
    )
    return GatewayFailure(
        kind, message, status_code=status_code, metadata=status_metadata
    )


def map_gateway_failure(error: GatewayFailure | Exception) -> DomainError:
    """Map gateway backend failures into the shared domain exception taxonomy."""

    if isinstance(error, DomainError):
        return error
    if not isinstance(error, GatewayFailure):
        return GatewayError(
            str(error) or error.__class__.__name__,
            retryable=False,
            metadata=(("failure_kind", GatewayFailureKind.UNKNOWN.value),),
        )

    metadata = error.metadata + (("failure_kind", error.kind.value),)
    if error.status_code is not None:
        metadata = metadata + (("status_code", str(error.status_code)),)

    if error.kind is GatewayFailureKind.BAD_REQUEST:
        return InvalidRequestError(str(error), metadata=metadata)
    if error.kind is GatewayFailureKind.UNAUTHENTICATED:
        return AuthenticationError(str(error), metadata=metadata)
    if error.kind is GatewayFailureKind.FORBIDDEN:
        return AuthorizationError(str(error), metadata=metadata)
    if error.kind is GatewayFailureKind.RATE_LIMITED:
        return QuotaExceededError(
            str(error), retryable=error.retryable, metadata=metadata
        )
    if error.kind is GatewayFailureKind.TIMEOUT:
        return TimeoutError(str(error), retryable=error.retryable, metadata=metadata)
    return GatewayError(str(error), retryable=error.retryable, metadata=metadata)

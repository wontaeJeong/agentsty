"""Internal auth token representations for gateway-bound requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..domain.errors import AuthenticationError
from ..domain.ids import TenantId
from ..domain.models import Metadata, normalize_metadata
from ..observability.tracing import TraceContext


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class InternalAuthToken:
    """Short-lived internal credential for audience-bound gateway access."""

    value: str
    issuer: str
    subject: str
    audience: str
    issued_at: datetime
    expires_at: datetime
    token_type: str = "Bearer"
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_value = self.value.strip()
        clean_issuer = self.issuer.strip()
        clean_subject = self.subject.strip()
        clean_audience = self.audience.strip()
        clean_token_type = self.token_type.strip()
        if not clean_value:
            raise ValueError("value must not be empty")
        if not clean_issuer:
            raise ValueError("issuer must not be empty")
        if not clean_subject:
            raise ValueError("subject must not be empty")
        if not clean_audience:
            raise ValueError("audience must not be empty")
        if not clean_token_type:
            raise ValueError("token_type must not be empty")
        object.__setattr__(self, "value", clean_value)
        object.__setattr__(self, "issuer", clean_issuer)
        object.__setattr__(self, "subject", clean_subject)
        object.__setattr__(self, "audience", clean_audience)
        object.__setattr__(self, "token_type", clean_token_type)
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("issued_at must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    def is_expired(self, *, at: datetime | None = None) -> bool:
        return self.expires_at <= (at or _utc_now())


@dataclass(frozen=True, slots=True)
class InternalAuthContext:
    """Resolved auth context attached to a single internal gateway call."""

    tenant_id: TenantId
    audience: str
    token: InternalAuthToken | None = None
    trace_context: TraceContext | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_audience = self.audience.strip()
        if not clean_audience:
            raise ValueError("audience must not be empty")
        if self.trace_context is not None and self.trace_context.tenant_id is not None:
            if self.trace_context.tenant_id != self.tenant_id:
                raise ValueError("trace context tenant must match auth context tenant")
        object.__setattr__(self, "audience", clean_audience)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    @property
    def authorization_header(self) -> str | None:
        if self.token is None:
            return None
        return f"{self.token.token_type} {self.token.value}"


class InternalAuthTokenProvider(Protocol):
    """Abstraction for issuing internal gateway tokens."""

    def issue_token(
        self,
        *,
        tenant_id: TenantId,
        audience: str,
        trace_context: TraceContext | None = None,
        metadata: Metadata = (),
    ) -> InternalAuthToken: ...


@dataclass(slots=True)
class StaticInternalAuthTokenProvider:
    """Simple short-lived token issuer for tests and local orchestration paths."""

    issuer: str = "agentsty-local"
    subject_prefix: str = "agentsty"
    ttl_seconds: int = 300
    _sequence: int = 0

    def __post_init__(self) -> None:
        if self.ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1")

    def issue_token(
        self,
        *,
        tenant_id: TenantId,
        audience: str,
        trace_context: TraceContext | None = None,
        metadata: Metadata = (),
    ) -> InternalAuthToken:
        issued_at = _utc_now()
        self._sequence += 1
        correlation_id = (
            trace_context.correlation_id if trace_context is not None else "no-trace"
        )
        token_value = (
            f"internal.{tenant_id.value}.{audience}.{self._sequence}.{correlation_id}"
        )
        return InternalAuthToken(
            value=token_value,
            issuer=self.issuer,
            subject=f"{self.subject_prefix}:{tenant_id.value}",
            audience=audience,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(seconds=self.ttl_seconds),
            metadata=metadata,
        )


def resolve_internal_auth_context(
    *,
    tenant_id: TenantId,
    audience: str,
    token_provider: InternalAuthTokenProvider | None,
    trace_context: TraceContext | None = None,
    allow_anonymous: bool,
    metadata: Metadata = (),
) -> InternalAuthContext:
    """Build and validate auth context for an internal gateway request."""

    if token_provider is None:
        if not allow_anonymous:
            raise AuthenticationError(
                "internal gateway authentication requires a token provider",
                metadata=(("audience", audience),),
            )
        return InternalAuthContext(
            tenant_id=tenant_id,
            audience=audience,
            trace_context=trace_context,
            metadata=normalize_metadata(metadata) + (("auth_mode", "anonymous_local"),),
        )

    token = token_provider.issue_token(
        tenant_id=tenant_id,
        audience=audience,
        trace_context=trace_context,
        metadata=metadata,
    )
    if token.audience != audience:
        raise AuthenticationError(
            "internal gateway token audience mismatch",
            metadata=(
                ("expected_audience", audience),
                ("token_audience", token.audience),
            ),
        )
    if token.is_expired():
        raise AuthenticationError(
            "internal gateway token is expired",
            metadata=(("audience", audience),),
        )
    return InternalAuthContext(
        tenant_id=tenant_id,
        audience=audience,
        token=token,
        trace_context=trace_context,
        metadata=normalize_metadata(metadata),
    )

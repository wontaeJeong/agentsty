"""Trace and correlation context helpers shared across platform layers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from uuid import uuid4

from ..domain.ids import JobId, RequestId, TenantId
from ..domain.models import Metadata, normalize_metadata


def _clean_optional(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} must not be blank")
    return cleaned


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Tenant-aware correlation context propagated across observability surfaces."""

    correlation_id: str
    tenant_id: TenantId | None = None
    request_id: RequestId | None = None
    job_id: JobId | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_correlation_id = self.correlation_id.strip()
        if not clean_correlation_id:
            raise ValueError("correlation id must not be empty")
        if self.request_id is not None and self.job_id is not None:
            if self.request_id.tenant_id != self.job_id.tenant_id:
                raise ValueError("request and job ids must share the same tenant")

        effective_tenant = self.tenant_id
        if effective_tenant is None:
            if self.request_id is not None:
                effective_tenant = self.request_id.tenant_id
            elif self.job_id is not None:
                effective_tenant = self.job_id.tenant_id

        if self.request_id is not None and effective_tenant is not None:
            if self.request_id.tenant_id != effective_tenant:
                raise ValueError("request id tenant must match trace context tenant")
        if self.job_id is not None and effective_tenant is not None:
            if self.job_id.tenant_id != effective_tenant:
                raise ValueError("job id tenant must match trace context tenant")

        object.__setattr__(self, "correlation_id", clean_correlation_id)
        object.__setattr__(self, "tenant_id", effective_tenant)
        object.__setattr__(self, "trace_id", _clean_optional("trace id", self.trace_id))
        object.__setattr__(self, "span_id", _clean_optional("span id", self.span_id))
        object.__setattr__(
            self,
            "parent_span_id",
            _clean_optional("parent span id", self.parent_span_id),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    @classmethod
    def new(
        cls,
        *,
        tenant_id: TenantId | None = None,
        request_id: RequestId | None = None,
        job_id: JobId | None = None,
        metadata: Metadata = (),
    ) -> TraceContext:
        return cls(
            correlation_id=uuid4().hex,
            trace_id=uuid4().hex,
            span_id=uuid4().hex[:16],
            tenant_id=tenant_id,
            request_id=request_id,
            job_id=job_id,
            metadata=metadata,
        )

    def child(
        self, *, span_id: str | None = None, metadata: Metadata = ()
    ) -> TraceContext:
        combined_metadata = self.metadata + normalize_metadata(metadata)
        return replace(
            self,
            span_id=_clean_optional("span id", span_id) or uuid4().hex[:16],
            parent_span_id=self.span_id,
            metadata=combined_metadata,
        )

    def bind(
        self,
        *,
        tenant_id: TenantId | None = None,
        request_id: RequestId | None = None,
        job_id: JobId | None = None,
        metadata: Metadata = (),
    ) -> TraceContext:
        combined_metadata = self.metadata + normalize_metadata(metadata)
        return replace(
            self,
            tenant_id=tenant_id if tenant_id is not None else self.tenant_id,
            request_id=request_id if request_id is not None else self.request_id,
            job_id=job_id if job_id is not None else self.job_id,
            metadata=combined_metadata,
        )

    def to_metadata(self) -> Metadata:
        entries: list[tuple[str, str]] = [("correlation_id", self.correlation_id)]
        if self.trace_id is not None:
            entries.append(("trace_id", self.trace_id))
        if self.span_id is not None:
            entries.append(("span_id", self.span_id))
        if self.parent_span_id is not None:
            entries.append(("parent_span_id", self.parent_span_id))
        if self.tenant_id is not None:
            entries.append(("tenant_id", self.tenant_id.value))
        if self.request_id is not None:
            entries.append(("request_id", self.request_id.value))
        if self.job_id is not None:
            entries.append(("job_id", self.job_id.value))
        entries.extend(self.metadata)
        return tuple(entries)


_TRACE_CONTEXT_VAR: ContextVar[TraceContext | None] = ContextVar(
    "agentsty_trace_context",
    default=None,
)


def current_trace_context() -> TraceContext | None:
    """Return the currently attached trace context, if one exists."""

    return _TRACE_CONTEXT_VAR.get()


@contextmanager
def attach_trace_context(context: TraceContext) -> Iterator[TraceContext]:
    """Temporarily attach a trace context for downstream logging and metrics."""

    token: Token[TraceContext | None] = _TRACE_CONTEXT_VAR.set(context)
    try:
        yield context
    finally:
        _TRACE_CONTEXT_VAR.reset(token)

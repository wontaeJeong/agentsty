"""Structured logging primitives with safe metadata redaction."""

from __future__ import annotations

import json
import logging as stdlib_logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

from ..domain.models import Metadata, normalize_metadata
from .tracing import TraceContext, current_trace_context

JsonValue = str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]

_REDACTED = "[REDACTED]"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class LogSeverity(StrEnum):
    """Stable severity taxonomy for structured platform events."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @property
    def logging_level(self) -> int:
        return cast(int, getattr(stdlib_logging, self.value))


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Key-based redaction rules for sensitive structured event attributes."""

    sensitive_keys: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "api_key",
                "authorization",
                "cookie",
                "password",
                "secret",
                "token",
            }
        )
    )
    mask: str = _REDACTED

    def __post_init__(self) -> None:
        if not self.mask:
            raise ValueError("redaction mask must not be empty")
        normalized_keys = frozenset(
            key.strip().lower() for key in self.sensitive_keys if key.strip()
        )
        object.__setattr__(self, "sensitive_keys", normalized_keys)

    def should_redact(self, key: str) -> bool:
        normalized = key.strip().lower().replace("-", "_")
        if not normalized:
            return False
        return normalized in self.sensitive_keys or any(
            marker in normalized
            for marker in (
                "secret",
                "token",
                "password",
                "authorization",
                "cookie",
                "api_key",
                "access_key",
            )
        )

    def redact_mapping(self, data: Mapping[str, object]) -> dict[str, JsonValue]:
        return {key: self._redact_value(key, value) for key, value in data.items()}

    def _redact_value(self, key: str, value: object) -> JsonValue:
        if self.should_redact(key):
            return self.mask
        if isinstance(value, Mapping):
            mapping_value = cast(Mapping[object, object], value)
            return {
                str(nested_key): self._redact_value(str(nested_key), nested_value)
                for nested_key, nested_value in mapping_value.items()
            }
        if isinstance(value, list | tuple):
            sequence_value = cast(list[object] | tuple[object, ...], value)
            return [self._redact_value(key, item) for item in sequence_value]
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return repr(value)


@dataclass(frozen=True, slots=True)
class StructuredLogEvent:
    """Structured platform event ready for emission to any logging backend."""

    event_name: str
    message: str
    severity: LogSeverity = LogSeverity.INFO
    service_name: str = "agentsty-platform"
    occurred_at: datetime = field(default_factory=_utc_now)
    trace_context: TraceContext | None = None
    attributes: dict[str, JsonValue] = field(default_factory=dict)
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_event_name = self.event_name.strip()
        clean_message = self.message.strip()
        clean_service_name = self.service_name.strip()
        if not clean_event_name:
            raise ValueError("event_name must not be empty")
        if not clean_message:
            raise ValueError("message must not be empty")
        if not clean_service_name:
            raise ValueError("service_name must not be empty")
        _require_aware_datetime("occurred_at", self.occurred_at)
        object.__setattr__(self, "event_name", clean_event_name)
        object.__setattr__(self, "message", clean_message)
        object.__setattr__(self, "service_name", clean_service_name)
        object.__setattr__(self, "attributes", dict(self.attributes))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    def to_payload(
        self,
        *,
        redaction_policy: RedactionPolicy | None = None,
    ) -> dict[str, JsonValue]:
        policy = redaction_policy or RedactionPolicy()
        trace_context = self.trace_context
        payload: dict[str, JsonValue] = {
            "event": self.event_name,
            "message": self.message,
            "severity": self.severity.value,
            "service": self.service_name,
            "timestamp": self.occurred_at.isoformat(),
            "attributes": policy.redact_mapping(self.attributes),
            "metadata": {key: value for key, value in self.metadata},
        }
        if trace_context is not None:
            payload["correlation_id"] = trace_context.correlation_id
            if trace_context.trace_id is not None:
                payload["trace_id"] = trace_context.trace_id
            if trace_context.span_id is not None:
                payload["span_id"] = trace_context.span_id
            if trace_context.tenant_id is not None:
                payload["tenant_id"] = trace_context.tenant_id.value
            if trace_context.request_id is not None:
                payload["request_id"] = trace_context.request_id.value
            if trace_context.job_id is not None:
                payload["job_id"] = trace_context.job_id.value
        return payload


@dataclass(slots=True)
class StructuredLogger:
    """Small backend-agnostic logger facade that emits JSON payloads."""

    service_name: str = "agentsty-platform"
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)
    logger_name: str = "agentsty.platform"

    def event(
        self,
        event_name: str,
        message: str,
        *,
        severity: LogSeverity = LogSeverity.INFO,
        trace_context: TraceContext | None = None,
        attributes: Mapping[str, object] | None = None,
        metadata: Metadata = (),
    ) -> StructuredLogEvent:
        return StructuredLogEvent(
            event_name=event_name,
            message=message,
            severity=severity,
            service_name=self.service_name,
            trace_context=trace_context or current_trace_context(),
            attributes=self.redaction_policy.redact_mapping(attributes or {}),
            metadata=metadata,
        )

    def emit(
        self,
        event_name: str,
        message: str,
        *,
        severity: LogSeverity = LogSeverity.INFO,
        trace_context: TraceContext | None = None,
        attributes: Mapping[str, object] | None = None,
        metadata: Metadata = (),
        logger: stdlib_logging.Logger | None = None,
    ) -> StructuredLogEvent:
        event = self.event(
            event_name,
            message,
            severity=severity,
            trace_context=trace_context,
            attributes=attributes,
            metadata=metadata,
        )
        target = logger or stdlib_logging.getLogger(self.logger_name)
        payload = event.to_payload(redaction_policy=self.redaction_policy)
        target.log(event.severity.logging_level, json.dumps(payload, sort_keys=True))
        return event

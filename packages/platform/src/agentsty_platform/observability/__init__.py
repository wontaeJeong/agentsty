"""Observability boundary for logging, metrics, tracing, and health signals."""

from __future__ import annotations

from importlib import import_module
from typing import cast

HealthComponent: object
HealthReport: object
HealthStatus: object
LogSeverity: object
MetricKind: object
MetricPoint: object
MetricRecorder: object
ReadinessCheck: object
ReadinessReport: object
ReadinessRequirement: object
RedactionPolicy: object
StructuredLogEvent: object
StructuredLogger: object
TraceContext: object
attach_trace_context: object
current_trace_context: object

_LOGGING_EXPORTS = {
    "LogSeverity",
    "RedactionPolicy",
    "StructuredLogEvent",
    "StructuredLogger",
}
_METRICS_EXPORTS = {
    "MetricKind",
    "MetricPoint",
    "MetricRecorder",
}
_TRACING_EXPORTS = {
    "TraceContext",
    "attach_trace_context",
    "current_trace_context",
}
_HEALTH_EXPORTS = {
    "HealthComponent",
    "HealthReport",
    "HealthStatus",
    "ReadinessCheck",
    "ReadinessReport",
    "ReadinessRequirement",
}

__all__ = [
    "HealthComponent",
    "HealthReport",
    "HealthStatus",
    "LogSeverity",
    "MetricKind",
    "MetricPoint",
    "MetricRecorder",
    "ReadinessCheck",
    "ReadinessReport",
    "ReadinessRequirement",
    "RedactionPolicy",
    "StructuredLogEvent",
    "StructuredLogger",
    "TraceContext",
    "attach_trace_context",
    "current_trace_context",
]


def __getattr__(name: str) -> object:
    """Lazily expose observability symbols without eager package-local imports."""

    if name in _LOGGING_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.observability.logging"), name),
        )
    if name in _METRICS_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.observability.metrics"), name),
        )
    if name in _TRACING_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.observability.tracing"), name),
        )
    if name in _HEALTH_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.observability.health"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Vendor-neutral metric recording surfaces for counters and timings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from .tracing import TraceContext, current_trace_context

JsonScalar = str | int | float | bool | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class MetricKind(StrEnum):
    """Stable metric kinds that downstream vendors can map later."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """Single metric observation with optional correlation context."""

    name: str
    kind: MetricKind
    value: float
    unit: str = "count"
    recorded_at: datetime = field(default_factory=_utc_now)
    attributes: dict[str, JsonScalar] = field(default_factory=dict)
    trace_context: TraceContext | None = None

    def __post_init__(self) -> None:
        clean_name = self.name.strip()
        clean_unit = self.unit.strip()
        if not clean_name:
            raise ValueError("metric name must not be empty")
        if not clean_unit:
            raise ValueError("metric unit must not be empty")
        _require_aware_datetime("recorded_at", self.recorded_at)
        if self.kind == MetricKind.COUNTER and self.value < 0:
            raise ValueError("counter metrics must not record negative values")
        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "unit", clean_unit)
        object.__setattr__(self, "attributes", dict(self.attributes))

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "kind": self.kind.value,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.recorded_at.isoformat(),
            "attributes": dict(self.attributes),
        }
        if self.trace_context is not None:
            payload["correlation_id"] = self.trace_context.correlation_id
            if self.trace_context.tenant_id is not None:
                payload["tenant_id"] = self.trace_context.tenant_id.value
            if self.trace_context.request_id is not None:
                payload["request_id"] = self.trace_context.request_id.value
            if self.trace_context.job_id is not None:
                payload["job_id"] = self.trace_context.job_id.value
        return payload


@dataclass(slots=True)
class MetricRecorder:
    """In-process metric capture facade for future backend adapters."""

    points: list[MetricPoint] = field(default_factory=list)

    def record(
        self,
        name: str,
        value: float,
        *,
        kind: MetricKind,
        unit: str,
        attributes: Mapping[str, JsonScalar] | None = None,
        trace_context: TraceContext | None = None,
    ) -> MetricPoint:
        point = MetricPoint(
            name=name,
            kind=kind,
            value=value,
            unit=unit,
            attributes=dict(attributes or {}),
            trace_context=trace_context or current_trace_context(),
        )
        self.points.append(point)
        return point

    def increment_counter(
        self,
        name: str,
        *,
        delta: int | float = 1,
        attributes: Mapping[str, JsonScalar] | None = None,
        trace_context: TraceContext | None = None,
    ) -> MetricPoint:
        return self.record(
            name,
            float(delta),
            kind=MetricKind.COUNTER,
            unit="count",
            attributes=attributes,
            trace_context=trace_context,
        )

    def record_duration(
        self,
        name: str,
        duration_seconds: float,
        *,
        attributes: Mapping[str, JsonScalar] | None = None,
        trace_context: TraceContext | None = None,
    ) -> MetricPoint:
        if duration_seconds < 0:
            raise ValueError("duration metrics must not record negative values")
        return self.record(
            name,
            duration_seconds,
            kind=MetricKind.HISTOGRAM,
            unit="seconds",
            attributes=attributes,
            trace_context=trace_context,
        )

    def snapshot(self) -> tuple[MetricPoint, ...]:
        return tuple(self.points)

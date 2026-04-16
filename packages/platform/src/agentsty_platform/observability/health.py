"""Health and readiness domain models for future API exposure."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..domain.models import Metadata, normalize_metadata


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class HealthStatus(StrEnum):
    """Aggregate service health taxonomy."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthComponent:
    """Single dependency or subsystem health observation."""

    name: str
    status: HealthStatus
    detail: str | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_name = self.name.strip()
        if not clean_name:
            raise ValueError("health component name must not be empty")
        clean_detail = None if self.detail is None else self.detail.strip()
        if clean_detail == "":
            raise ValueError("health component detail must not be blank")
        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "detail", clean_detail)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Snapshot of overall service health for a future `/health` endpoint."""

    service_name: str
    status: HealthStatus
    checked_at: datetime = field(default_factory=_utc_now)
    components: tuple[HealthComponent, ...] = field(default_factory=tuple)
    summary: str | None = None

    def __post_init__(self) -> None:
        clean_service_name = self.service_name.strip()
        if not clean_service_name:
            raise ValueError("health report service_name must not be empty")
        _require_aware_datetime("checked_at", self.checked_at)
        object.__setattr__(self, "service_name", clean_service_name)
        object.__setattr__(self, "components", tuple(self.components))

    @classmethod
    def from_components(
        cls,
        service_name: str,
        components: tuple[HealthComponent, ...],
        *,
        checked_at: datetime | None = None,
        summary: str | None = None,
    ) -> HealthReport:
        status = HealthStatus.HEALTHY
        if any(component.status is HealthStatus.UNHEALTHY for component in components):
            status = HealthStatus.UNHEALTHY
        elif any(component.status is HealthStatus.DEGRADED for component in components):
            status = HealthStatus.DEGRADED
        return cls(
            service_name=service_name,
            status=status,
            checked_at=checked_at or _utc_now(),
            components=components,
            summary=summary,
        )


class ReadinessRequirement(StrEnum):
    """Whether a readiness check is mandatory for serving traffic."""

    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """Single readiness gate for a future `/ready` endpoint."""

    name: str
    ready: bool
    requirement: ReadinessRequirement = ReadinessRequirement.REQUIRED
    detail: str | None = None
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_name = self.name.strip()
        if not clean_name:
            raise ValueError("readiness check name must not be empty")
        clean_detail = None if self.detail is None else self.detail.strip()
        if clean_detail == "":
            raise ValueError("readiness check detail must not be blank")
        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "detail", clean_detail)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Snapshot of traffic readiness independent of transport semantics."""

    service_name: str
    ready: bool
    checked_at: datetime = field(default_factory=_utc_now)
    checks: tuple[ReadinessCheck, ...] = field(default_factory=tuple)
    blocking_checks: tuple[str, ...] = field(default_factory=tuple)
    summary: str | None = None

    def __post_init__(self) -> None:
        clean_service_name = self.service_name.strip()
        if not clean_service_name:
            raise ValueError("readiness report service_name must not be empty")
        _require_aware_datetime("checked_at", self.checked_at)
        object.__setattr__(self, "service_name", clean_service_name)
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blocking_checks", tuple(self.blocking_checks))

    @classmethod
    def from_checks(
        cls,
        service_name: str,
        checks: tuple[ReadinessCheck, ...],
        *,
        checked_at: datetime | None = None,
        summary: str | None = None,
    ) -> ReadinessReport:
        blocking_checks = tuple(
            check.name
            for check in checks
            if check.requirement is ReadinessRequirement.REQUIRED and not check.ready
        )
        return cls(
            service_name=service_name,
            ready=not blocking_checks,
            checked_at=checked_at or _utc_now(),
            checks=checks,
            blocking_checks=blocking_checks,
            summary=summary,
        )

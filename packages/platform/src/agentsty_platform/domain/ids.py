"""Tenant-aware identifiers shared across platform boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import override

_SCOPED_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TENANT_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _validate_scoped_id(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if not _SCOPED_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} must use only letters, digits, '.', ':', '_' or '-'")
    return normalized


@dataclass(frozen=True, slots=True)
class TenantId:
    """Stable tenant identifier used to scope all execution resources."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not _TENANT_ID_PATTERN.fullmatch(normalized):
            raise ValueError(
                "tenant id must be 1-63 chars of lowercase letters, digits, or '-'"
            )
        object.__setattr__(self, "value", normalized)

    @override
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Opaque client-supplied key used to deduplicate request submission."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("idempotency key must not be empty")
        if len(normalized) > 255:
            raise ValueError("idempotency key must be at most 255 characters")
        object.__setattr__(self, "value", normalized)

    @override
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RequestId:
    """Tenant-scoped request identifier."""

    tenant_id: TenantId
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_scoped_id("request id", self.value))

    @property
    def scoped_value(self) -> str:
        return f"{self.tenant_id}:{self.value}"

    @override
    def __str__(self) -> str:
        return self.scoped_value


@dataclass(frozen=True, slots=True)
class JobId:
    """Tenant-scoped execution job identifier."""

    tenant_id: TenantId
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_scoped_id("job id", self.value))

    @property
    def scoped_value(self) -> str:
        return f"{self.tenant_id}:{self.value}"

    @override
    def __str__(self) -> str:
        return self.scoped_value

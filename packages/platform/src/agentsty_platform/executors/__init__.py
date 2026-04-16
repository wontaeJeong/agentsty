"""Sandbox executor boundary for pluggable execution contracts and adapters."""

from __future__ import annotations

from importlib import import_module
from typing import cast

SandboxExecutor: object
SandboxCapabilities: object
SandboxCancellationReceipt: object
SandboxCancellationRequest: object
SandboxCleanupRequest: object
SandboxCleanupResult: object
SandboxCreateRequest: object
SandboxHandle: object
SandboxInspection: object
SandboxIsolationMode: object
SandboxLaunchReceipt: object
SandboxLaunchRequest: object
SandboxProgramSpec: object
SandboxResourceIdentity: object
SandboxResourceRequirements: object
SandboxStatus: object
TenantResourceBoundary: object
status_for_error: object

_CONTRACT_EXPORTS = {
    "SandboxCapabilities",
    "SandboxCancellationReceipt",
    "SandboxCancellationRequest",
    "SandboxCleanupRequest",
    "SandboxCleanupResult",
    "SandboxCreateRequest",
    "SandboxHandle",
    "SandboxInspection",
    "SandboxIsolationMode",
    "SandboxLaunchReceipt",
    "SandboxLaunchRequest",
    "SandboxProgramSpec",
    "SandboxResourceIdentity",
    "SandboxResourceRequirements",
    "SandboxStatus",
    "TenantResourceBoundary",
    "status_for_error",
}

__all__ = [
    "SandboxCapabilities",
    "SandboxCancellationReceipt",
    "SandboxCancellationRequest",
    "SandboxCleanupRequest",
    "SandboxCleanupResult",
    "SandboxCreateRequest",
    "SandboxExecutor",
    "SandboxHandle",
    "SandboxInspection",
    "SandboxIsolationMode",
    "SandboxLaunchReceipt",
    "SandboxLaunchRequest",
    "SandboxProgramSpec",
    "SandboxResourceIdentity",
    "SandboxResourceRequirements",
    "SandboxStatus",
    "TenantResourceBoundary",
    "status_for_error",
]


def __getattr__(name: str) -> object:
    """Lazily expose executor symbols without eager package-local imports."""

    if name == "SandboxExecutor":
        return cast(
            object,
            import_module("agentsty_platform.executors.adapter").SandboxExecutor,
        )
    if name in _CONTRACT_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.executors.contracts"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

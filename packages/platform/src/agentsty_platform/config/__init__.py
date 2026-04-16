"""Configuration boundary for platform settings and environment profiles."""

from __future__ import annotations

from importlib import import_module
from typing import cast

APISettings: object
AuthSettings: object
EnvironmentProfile: object
ExecutorSettings: object
GatewaySettings: object
KubernetesSettings: object
ObservabilitySettings: object
PersistenceSettings: object
PlatformSettings: object
RuntimeSettings: object
TimeoutSettings: object

_SETTINGS_EXPORTS = {
    "APISettings",
    "AuthSettings",
    "ExecutorSettings",
    "GatewaySettings",
    "KubernetesSettings",
    "ObservabilitySettings",
    "PersistenceSettings",
    "PlatformSettings",
    "RuntimeSettings",
    "TimeoutSettings",
}

__all__ = [
    "APISettings",
    "AuthSettings",
    "EnvironmentProfile",
    "ExecutorSettings",
    "GatewaySettings",
    "KubernetesSettings",
    "ObservabilitySettings",
    "PersistenceSettings",
    "PlatformSettings",
    "RuntimeSettings",
    "TimeoutSettings",
]


def __getattr__(name: str) -> object:
    """Lazily expose config symbols without eager package-local imports."""

    if name == "EnvironmentProfile":
        return cast(
            object,
            import_module("agentsty_platform.config.profiles").EnvironmentProfile,
        )
    if name in _SETTINGS_EXPORTS:
        return cast(
            object, getattr(import_module("agentsty_platform.config.settings"), name)
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

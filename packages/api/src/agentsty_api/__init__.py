"""Transport-oriented FastAPI surface for agentsty."""

from __future__ import annotations

from importlib import import_module
from typing import Final

create_app: object
APIDependencies: object
ExecutionTemplate: object

__all__ = [
    "APP_NAME",
    "APIDependencies",
    "DISTRO_NAME",
    "ExecutionTemplate",
    "PACKAGE_NAME",
    "PLATFORM_PACKAGE",
    "__version__",
    "create_app",
    "package_metadata",
]

PACKAGE_NAME: Final[str] = "agentsty_api"
DISTRO_NAME: Final[str] = "agentsty-api"
APP_NAME: Final[str] = "agentsty-api"
PLATFORM_PACKAGE: Final[str] = "agentsty_platform"
__version__: Final[str] = "0.0.0"


def package_metadata() -> dict[str, str]:
    """Return minimal package identity metadata."""

    return {
        "package_name": PACKAGE_NAME,
        "distribution_name": DISTRO_NAME,
        "app_name": APP_NAME,
        "platform_package": PLATFORM_PACKAGE,
        "version": __version__,
    }


def __getattr__(name: str) -> object:
    """Lazily expose FastAPI entrypoints without eager imports."""

    if name == "create_app":
        return getattr(import_module("agentsty_api.app"), name)
    if name in {"APIDependencies", "ExecutionTemplate"}:
        return getattr(import_module("agentsty_api.dependencies"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

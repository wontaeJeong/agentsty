"""Shared production platform boundaries for agentsty."""

from __future__ import annotations

from typing import Final

__all__ = [
    "BOUNDARY_PACKAGES",
    "DISTRO_NAME",
    "PACKAGE_NAME",
    "__version__",
    "package_metadata",
]

PACKAGE_NAME: Final[str] = "agentsty_platform"
DISTRO_NAME: Final[str] = "agentsty-platform"
BOUNDARY_PACKAGES: Final[tuple[str, ...]] = (
    "config",
    "domain",
    "services",
    "gateway",
    "persistence",
    "observability",
    "executors",
    "runtimes",
)
__version__: Final[str] = "0.0.0"


def package_metadata() -> dict[str, str | tuple[str, ...]]:
    """Return platform package identity and boundary metadata."""

    return {
        "package_name": PACKAGE_NAME,
        "distribution_name": DISTRO_NAME,
        "version": __version__,
        "boundaries": BOUNDARY_PACKAGES,
    }

"""Environment profile defaults for the platform settings layer."""

from __future__ import annotations

from enum import StrEnum


class EnvironmentProfile(StrEnum):
    """Supported environment profiles for shared platform configuration."""

    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        """Return whether the profile should enforce production-grade controls."""

        return self in {self.STAGING, self.PRODUCTION}

    @classmethod
    def default(cls) -> EnvironmentProfile:
        """Return the default profile when no override is provided."""

        return cls.LOCAL

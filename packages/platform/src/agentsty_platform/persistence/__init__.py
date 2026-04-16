"""Persistence boundary for repositories and artifact storage concerns."""

from __future__ import annotations

from importlib import import_module
from typing import cast

ArtifactContentRef: object
ArtifactMetadataRecord: object
ArtifactContentStore: object
ArtifactMetadataRepository: object
AuditEvent: object
AuditMetadata: object
IdempotencyRecord: object
InMemoryArtifactMetadataRepository: object
InMemoryJobRepository: object
JobRecord: object
JobRepository: object
LocalFileArtifactContentStore: object
LocalPersistence: object
NonLocalPersistence: object
NonLocalPersistencePaths: object
PersistentArtifactMetadataRepository: object
PersistentJobRepository: object
SqliteArtifactMetadataRepository: object
SqliteJobRepository: object
build_non_local_persistence: object

_MODEL_EXPORTS = {
    "ArtifactContentRef",
    "ArtifactMetadataRecord",
    "AuditEvent",
    "AuditMetadata",
    "IdempotencyRecord",
    "JobRecord",
}
_REPOSITORY_EXPORTS = {
    "ArtifactContentStore",
    "ArtifactMetadataRepository",
    "JobRepository",
}
_LOCAL_EXPORTS = {
    "InMemoryArtifactMetadataRepository",
    "InMemoryJobRepository",
    "LocalFileArtifactContentStore",
    "LocalPersistence",
}
_NON_LOCAL_EXPORTS = {
    "NonLocalPersistence",
    "NonLocalPersistencePaths",
    "PersistentArtifactMetadataRepository",
    "PersistentJobRepository",
    "SqliteArtifactMetadataRepository",
    "SqliteJobRepository",
    "build_non_local_persistence",
}

__all__ = [
    "ArtifactContentRef",
    "ArtifactContentStore",
    "ArtifactMetadataRecord",
    "ArtifactMetadataRepository",
    "AuditEvent",
    "AuditMetadata",
    "IdempotencyRecord",
    "InMemoryArtifactMetadataRepository",
    "InMemoryJobRepository",
    "JobRecord",
    "JobRepository",
    "LocalFileArtifactContentStore",
    "LocalPersistence",
    "NonLocalPersistence",
    "NonLocalPersistencePaths",
    "PersistentArtifactMetadataRepository",
    "PersistentJobRepository",
    "SqliteArtifactMetadataRepository",
    "SqliteJobRepository",
    "build_non_local_persistence",
]


def __getattr__(name: str) -> object:
    """Lazily expose persistence symbols without eager package-local imports."""

    if name in _MODEL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.persistence.models"), name),
        )
    if name in _REPOSITORY_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.persistence.repositories"), name),
        )
    if name in _LOCAL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.persistence.local"), name),
        )
    if name in _NON_LOCAL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.persistence.nonlocal"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

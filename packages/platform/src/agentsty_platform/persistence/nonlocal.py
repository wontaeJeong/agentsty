"""Non-local persistence composition backed by a durable SQL store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .local import LocalFileArtifactContentStore
from .repositories import (
    ArtifactContentStore,
    ArtifactMetadataRepository,
    JobRepository,
)
from .sqlite import SqliteArtifactMetadataRepository, SqliteJobRepository


class _RuntimeSettingsLike(Protocol):
    workspace_root: Path


class _PersistenceSettingsLike(Protocol):
    database_url: str
    artifact_root: Path


class _SettingsLike(Protocol):
    runtime: _RuntimeSettingsLike
    persistence: _PersistenceSettingsLike


@dataclass(frozen=True, slots=True)
class NonLocalPersistencePaths:
    """Filesystem locations used by non-local durable persistence wiring."""

    root: Path
    database_path: Path
    migrations_root: Path

    @classmethod
    def from_settings(cls, settings: _SettingsLike) -> NonLocalPersistencePaths:
        runtime_root = Path(settings.runtime.workspace_root)
        root = runtime_root / "_service_state"
        database_path = root / "nonlocal-persistence.sqlite3"
        if settings.persistence.database_url.startswith("sqlite:///"):
            database_path = Path(
                settings.persistence.database_url.removeprefix("sqlite:///")
            )
        return cls(
            root=root,
            database_path=database_path,
            migrations_root=Path(__file__).with_name("migrations"),
        )


@dataclass(frozen=True, slots=True)
class NonLocalPersistence:
    """Typed bundle for the production-oriented non-local persistence composition."""

    jobs: JobRepository[object, object]
    artifact_metadata: ArtifactMetadataRepository
    artifact_content: ArtifactContentStore
    paths: NonLocalPersistencePaths


PersistentJobRepository = SqliteJobRepository
PersistentArtifactMetadataRepository = SqliteArtifactMetadataRepository


def build_non_local_persistence(settings: _SettingsLike) -> NonLocalPersistence:
    """Create the non-local persistence bundle for default dependency wiring."""

    paths = NonLocalPersistencePaths.from_settings(settings)
    database_url = settings.persistence.database_url
    if database_url.startswith("postgresql"):
        raise ValueError(
            "non-local persistence does not provide a PostgreSQL backend yet; configure a supported sqlite:/// URL instead of relying on a SQLite rewrite"
        )
    return NonLocalPersistence(
        jobs=PersistentJobRepository(database_url),
        artifact_metadata=PersistentArtifactMetadataRepository(database_url),
        artifact_content=LocalFileArtifactContentStore(
            settings.persistence.artifact_root
        ),
        paths=paths,
    )

"""Small shared value models for execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

MetadataEntry = tuple[str, str]
Metadata = tuple[MetadataEntry, ...]


def normalize_metadata(metadata: Metadata) -> Metadata:
    normalized: list[MetadataEntry] = []
    for key, value in metadata:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("metadata keys must not be empty")
        normalized.append((clean_key, value))
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ExecutionTimeouts:
    """Per-request timeout budget shared by services and executors."""

    request_timeout_seconds: int = 60
    execution_timeout_seconds: int = 900
    cancellation_grace_period_seconds: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.request_timeout_seconds <= 600:
            raise ValueError("request timeout must be between 1 and 600 seconds")
        if not 5 <= self.execution_timeout_seconds <= 3_600:
            raise ValueError("execution timeout must be between 5 and 3600 seconds")
        if self.request_timeout_seconds > self.execution_timeout_seconds:
            raise ValueError("request timeout must not exceed execution timeout")
        if not 1 <= self.cancellation_grace_period_seconds <= 300:
            raise ValueError(
                "cancellation grace period must be between 1 and 300 seconds"
            )


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    """Executor-neutral metadata describing a persisted execution artifact."""

    key: str
    media_type: str | None = None
    size_bytes: int = 0
    sha256: str | None = None
    redacted: bool = False
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_key = self.key.strip()
        if not clean_key:
            raise ValueError("artifact key must not be empty")
        if self.size_bytes < 0:
            raise ValueError("artifact size must not be negative")
        object.__setattr__(self, "key", clean_key)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ResultSummary:
    """Small result metadata intended for persistence and API summaries."""

    output_text: str | None = None
    duration_seconds: float | None = None
    artifact_count: int = 0
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("result duration must not be negative")
        if self.artifact_count < 0:
            raise ValueError("artifact count must not be negative")
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

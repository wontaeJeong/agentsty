from __future__ import annotations

import importlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


def _persistence_module() -> Any:
    return importlib.import_module("agentsty_platform.persistence")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


@pytest.mark.unit
def test_public_exports_and_job_lifecycle_are_stable() -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    started_at = submitted_at + timedelta(seconds=2)
    finished_at = started_at + timedelta(seconds=5)

    jobs = persistence.InMemoryJobRepository()

    reserved = jobs.reserve_idempotency(
        tenant,
        domain.IdempotencyKey("idem-1"),
        request_id,
        job_id,
        created_at=submitted_at,
        audit_metadata=persistence.AuditMetadata(actor="api", source="http"),
    )
    created = jobs.create(
        domain.ExecutionRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            idempotency_key=domain.IdempotencyKey("idem-1"),
            payload={"prompt": "hello"},
            submitted_at=submitted_at,
        )
    )
    jobs.mark_validated(tenant, job_id, updated_at=submitted_at)
    jobs.mark_queued(tenant, job_id, updated_at=submitted_at + timedelta(seconds=1))
    jobs.mark_starting(tenant, job_id, started_at=started_at)
    jobs.mark_running(tenant, job_id, updated_at=started_at)
    succeeded = jobs.mark_succeeded(
        tenant,
        job_id,
        finished_at=finished_at,
        payload={"message": "done"},
        summary=domain.ResultSummary(output_text="done", duration_seconds=5.0),
        artifacts=(
            domain.ArtifactSummary(
                key="logs/stdout.txt",
                media_type="text/plain",
                size_bytes=4,
            ),
        ),
    )

    assert created.state.status is domain.ExecutionStatus.RECEIVED
    assert reserved.request_id == request_id
    assert (
        jobs.find_by_idempotency_key(tenant, domain.IdempotencyKey("idem-1"))
        == reserved
    )
    assert jobs.get_by_request_id(tenant, request_id).result == succeeded.result
    assert succeeded.result is not None
    assert succeeded.result.status is domain.ExecutionStatus.SUCCEEDED
    assert succeeded.result.payload == {"message": "done"}
    assert succeeded.result.artifacts[0].key == "logs/stdout.txt"

    audit_events = jobs.list_audit_events(tenant, job_id)
    assert [event.event_type for event in audit_events] == [
        "idempotency_reserved",
        "job_created",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
    ]
    assert audit_events[-1].to_status is domain.ExecutionStatus.SUCCEEDED
    assert audit_events[0].audit_metadata.source == "http"


@pytest.mark.unit
def test_idempotency_and_lookup_remain_tenant_isolated() -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    tenant_a = domain.TenantId("tenant-a")
    tenant_b = domain.TenantId("tenant-b")
    jobs = persistence.InMemoryJobRepository()

    record_a = jobs.reserve_idempotency(
        tenant_a,
        domain.IdempotencyKey("same-key"),
        domain.RequestId(tenant_id=tenant_a, value="req-a"),
        domain.JobId(tenant_id=tenant_a, value="job-a"),
    )
    record_b = jobs.reserve_idempotency(
        tenant_b,
        domain.IdempotencyKey("same-key"),
        domain.RequestId(tenant_id=tenant_b, value="req-b"),
        domain.JobId(tenant_id=tenant_b, value="job-b"),
    )

    assert record_a.job_id.value == "job-a"
    assert record_b.job_id.value == "job-b"
    assert (
        jobs.find_by_idempotency_key(tenant_a, domain.IdempotencyKey("same-key"))
        == record_a
    )
    assert (
        jobs.find_by_idempotency_key(tenant_b, domain.IdempotencyKey("same-key"))
        == record_b
    )

    with pytest.raises(ValueError, match="different job"):
        _ = jobs.reserve_idempotency(
            tenant_a,
            domain.IdempotencyKey("same-key"),
            domain.RequestId(tenant_id=tenant_a, value="req-other"),
            domain.JobId(tenant_id=tenant_a, value="job-other"),
        )

    with pytest.raises(ValueError, match="lookup tenant"):
        _ = jobs.get(tenant_a, domain.JobId(tenant_id=tenant_b, value="job-b"))


@pytest.mark.unit
def test_artifact_metadata_and_content_storage_are_split(tmp_path: Path) -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    created_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    metadata_repo = persistence.InMemoryArtifactMetadataRepository()
    content_store = persistence.LocalFileArtifactContentStore(tmp_path / "artifacts")

    content_ref = content_store.write(tenant, job_id, "logs/stdout.txt", b"done")
    record = metadata_repo.put(
        persistence.ArtifactMetadataRecord(
            tenant_id=tenant,
            job_id=job_id,
            artifact=domain.ArtifactSummary(
                key="logs/stdout.txt",
                media_type="text/plain",
                size_bytes=4,
            ),
            created_at=created_at,
            content_ref=content_ref,
        )
    )

    serialized = json.loads(json.dumps(asdict(record), default=str))

    assert record.content_ref is not None
    assert record.content_ref.storage_backend == "local_fs"
    assert metadata_repo.get(tenant, job_id, "logs/stdout.txt") == record
    assert metadata_repo.list_for_job(tenant, job_id) == (record,)
    assert content_store.read(tenant, job_id, "logs/stdout.txt") == b"done"
    assert serialized["tenant_id"]["value"] == "tenant-a"
    assert serialized["artifact"]["key"] == "logs/stdout.txt"
    assert serialized["content_ref"]["locator"] == "tenant-a/job-1/logs/stdout.txt"

    with pytest.raises(ValueError, match="safe relative path"):
        _ = content_store.write(tenant, job_id, "../secrets.txt", b"nope")

    with pytest.raises(ValueError, match="lookup tenant"):
        _ = content_store.read(
            domain.TenantId("tenant-b"),
            job_id,
            "logs/stdout.txt",
        )


@pytest.mark.unit
def test_terminal_persistence_methods_require_matching_error_taxonomy() -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    started_at = submitted_at + timedelta(seconds=2)
    finished_at = started_at + timedelta(seconds=5)
    jobs = persistence.InMemoryJobRepository()

    jobs.create(
        domain.ExecutionRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            idempotency_key=domain.IdempotencyKey("idem-1"),
            payload={"prompt": "hello"},
            submitted_at=submitted_at,
        )
    )
    jobs.mark_validated(tenant, job_id, updated_at=submitted_at)
    jobs.mark_queued(tenant, job_id, updated_at=submitted_at + timedelta(seconds=1))
    jobs.mark_starting(tenant, job_id, started_at=started_at)
    jobs.mark_running(tenant, job_id, updated_at=started_at)

    with pytest.raises(ValueError, match="matching error details"):
        _ = jobs.mark_timed_out(
            tenant,
            job_id,
            finished_at=finished_at,
            error=domain.GatewayError("wrong category").as_details(),
        )

    cancelled = jobs.mark_cancelled(
        tenant,
        job_id,
        finished_at=finished_at,
        error=domain.CancellationError("operator requested cancel").as_details(),
    )

    assert cancelled.state.status is domain.ExecutionStatus.CANCELLED
    assert cancelled.result is not None
    assert cancelled.result.error.category is domain.ErrorCategory.CANCELLATION


@pytest.mark.unit
def test_non_local_sqlite_persistence_survives_repository_reloads(
    tmp_path: Path,
) -> None:
    persistence = _persistence_module()
    domain = _domain_module()
    gateway = importlib.import_module("agentsty_platform.gateway")

    database_url = f"sqlite:///{tmp_path / 'nonlocal.sqlite3'}"
    jobs = persistence.PersistentJobRepository(database_url)
    artifacts = persistence.PersistentArtifactMetadataRepository(database_url)
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-sql-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-sql-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
    started_at = submitted_at + timedelta(seconds=2)
    finished_at = started_at + timedelta(seconds=5)
    request = domain.ExecutionRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        idempotency_key=domain.IdempotencyKey("idem-sql-1"),
        payload=gateway.GatewayRequest(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(model="gpt-4.1"),
            messages=(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.USER,
                    content="hello durable repo",
                ),
            ),
        ),
        submitted_at=submitted_at,
    )

    _ = jobs.reserve_idempotency(
        tenant,
        request.idempotency_key,
        request_id,
        job_id,
        created_at=submitted_at,
        audit_metadata=persistence.AuditMetadata(actor="api", source="http"),
    )
    _ = jobs.create(request)
    _ = jobs.mark_validated(tenant, job_id, updated_at=submitted_at)
    _ = jobs.mark_queued(tenant, job_id, updated_at=submitted_at + timedelta(seconds=1))
    _ = jobs.mark_starting(tenant, job_id, started_at=started_at)
    _ = jobs.mark_running(tenant, job_id, updated_at=started_at)
    succeeded = jobs.mark_succeeded(
        tenant,
        job_id,
        finished_at=finished_at,
        payload=gateway.GatewayResponse(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(model="gpt-4.1"),
            message=gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.ASSISTANT,
                content="durable output",
            ),
        ),
        summary=domain.ResultSummary(
            output_text="durable output", duration_seconds=5.0
        ),
    )
    artifact = artifacts.put(
        persistence.ArtifactMetadataRecord(
            tenant_id=tenant,
            job_id=job_id,
            artifact=domain.ArtifactSummary(
                key="logs/stdout.txt",
                media_type="text/plain",
                size_bytes=14,
            ),
            created_at=finished_at,
        )
    )

    reloaded_jobs = persistence.PersistentJobRepository(database_url)
    reloaded_artifacts = persistence.PersistentArtifactMetadataRepository(database_url)

    reloaded = reloaded_jobs.get(tenant, job_id)
    audit_events = reloaded_jobs.list_audit_events(tenant, job_id)

    assert reloaded.state.status is domain.ExecutionStatus.SUCCEEDED
    assert reloaded.result == succeeded.result
    assert reloaded.request.payload.messages[0].content == "hello durable repo"
    assert reloaded_jobs.get_by_request_id(tenant, request_id) == reloaded
    assert (
        reloaded_jobs.find_by_idempotency_key(tenant, request.idempotency_key).job_id
        == job_id
    )
    assert reloaded_artifacts.get(tenant, job_id, "logs/stdout.txt") == artifact
    assert reloaded_artifacts.list_for_job(tenant, job_id) == (artifact,)
    assert [event.event_type for event in audit_events] == [
        "idempotency_reserved",
        "job_created",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
        "job_status_changed",
    ]


@pytest.mark.unit
def test_non_local_sqlite_persistence_runs_migrations_on_first_write(
    tmp_path: Path,
) -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    database_path = tmp_path / "migrated.sqlite3"
    jobs = persistence.PersistentJobRepository(f"sqlite:///{database_path}")
    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-migrate-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-migrate-1")
    submitted_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)

    _ = jobs.reserve_idempotency(
        tenant,
        domain.IdempotencyKey("idem-migrate-1"),
        request_id,
        job_id,
        created_at=submitted_at,
    )

    with sqlite3.connect(database_path) as connection:
        migration_versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert migration_versions == ["0001_nonlocal_persistence.sql"]
    assert {
        "jobs",
        "idempotency_records",
        "audit_events",
        "artifact_metadata",
    } <= table_names


@pytest.mark.unit
def test_non_local_persistence_rejects_postgresql_urls_instead_of_rewriting() -> None:
    persistence = _persistence_module()

    @dataclass(frozen=True, slots=True)
    class _RuntimeSettings:
        workspace_root: Path

    @dataclass(frozen=True, slots=True)
    class _PersistenceSettings:
        database_url: str
        artifact_root: Path

    @dataclass(frozen=True, slots=True)
    class _Settings:
        runtime: _RuntimeSettings
        persistence: _PersistenceSettings

    settings = _Settings(
        runtime=_RuntimeSettings(workspace_root=Path("/tmp/agentsty-runtime")),
        persistence=_PersistenceSettings(
            database_url="postgresql+psycopg://agentsty:secret@db.internal/agentsty",
            artifact_root=Path("/tmp/agentsty-artifacts"),
        ),
    )

    with pytest.raises(ValueError, match="does not provide a PostgreSQL backend"):
        _ = persistence.build_non_local_persistence(settings)


@pytest.mark.unit
def test_non_local_persistence_wires_artifact_byte_storage(tmp_path: Path) -> None:
    persistence = _persistence_module()
    domain = _domain_module()

    @dataclass(frozen=True, slots=True)
    class _RuntimeSettings:
        workspace_root: Path

    @dataclass(frozen=True, slots=True)
    class _PersistenceSettings:
        database_url: str
        artifact_root: Path

    @dataclass(frozen=True, slots=True)
    class _Settings:
        runtime: _RuntimeSettings
        persistence: _PersistenceSettings

    settings = _Settings(
        runtime=_RuntimeSettings(workspace_root=tmp_path / "runtime"),
        persistence=_PersistenceSettings(
            database_url=f"sqlite:///{tmp_path / 'nonlocal.sqlite3'}",
            artifact_root=tmp_path / "artifact-store",
        ),
    )
    non_local = persistence.build_non_local_persistence(settings)
    tenant = domain.TenantId("tenant-a")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")

    content_ref = non_local.artifact_content.write(
        tenant,
        job_id,
        "opencode/session-export.json",
        b'{"ok":true}',
    )

    assert content_ref.storage_backend == "local_fs"
    assert (
        non_local.artifact_content.read(tenant, job_id, "opencode/session-export.json")
        == b'{"ok":true}'
    )

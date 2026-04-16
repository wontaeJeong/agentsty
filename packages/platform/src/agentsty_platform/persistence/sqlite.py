"""SQLite-backed durable persistence implementations for non-local execution."""

# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module, resources
from pathlib import Path
from threading import Lock
from typing import Any, Generic, TypeVar, cast

from ..domain.errors import ErrorCategory, ErrorDetails
from ..domain.execution import (
    CancellationState,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    TimeoutState,
)
from ..domain.ids import IdempotencyKey, JobId, RequestId, TenantId
from ..domain.models import ArtifactSummary, ResultSummary
from .models import (
    ArtifactMetadataRecord,
    AuditEvent,
    AuditMetadata,
    IdempotencyRecord,
    JobRecord,
)

RequestPayloadT = TypeVar("RequestPayloadT")
ResultPayloadT = TypeVar("ResultPayloadT")

_MIGRATIONS_PACKAGE = "agentsty_platform.persistence.migrations"


def _resolve_symbol(symbol_path: str) -> type[Any]:
    module_name, _, qualname = symbol_path.partition(":")
    if not module_name or not qualname:
        raise ValueError(f"invalid persisted symbol path: {symbol_path!r}")
    symbol: Any = import_module(module_name)
    for part in qualname.split("."):
        symbol = getattr(symbol, part)
    return cast(type[Any], symbol)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return {
            "__enum__": f"{value.__class__.__module__}:{value.__class__.__qualname__}",
            "value": value.value,
        }
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, Path):
        return {"__path__": str(value)}
    if is_dataclass(value):
        return {
            "__type__": f"{type(value).__module__}:{type(value).__qualname__}",
            "fields": {
                field.name: _to_jsonable(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, tuple):
        return {"__tuple__": [_to_jsonable(item) for item in value]}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    raise TypeError(f"unsupported persisted value: {type(value)!r}")


def _from_jsonable(value: Any) -> Any:
    if isinstance(value, list):
        return [_from_jsonable(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "__datetime__" in value:
        return datetime.fromisoformat(cast(str, value["__datetime__"]))
    if "__path__" in value:
        return Path(cast(str, value["__path__"]))
    if "__enum__" in value:
        enum_type = _resolve_symbol(cast(str, value["__enum__"]))
        return enum_type(value["value"])
    if "__tuple__" in value:
        return tuple(
            _from_jsonable(item) for item in cast(list[Any], value["__tuple__"])
        )
    if "__type__" in value:
        value_type = _resolve_symbol(cast(str, value["__type__"]))
        raw_fields = cast(dict[str, Any], value["fields"])
        restored_fields = {
            key: _from_jsonable(item) for key, item in raw_fields.items()
        }
        return value_type(**restored_fields)
    return {key: _from_jsonable(item) for key, item in value.items()}


def _encode_record(value: Any) -> str:
    return json.dumps(_to_jsonable(value), separators=(",", ":"), sort_keys=True)


def _decode_record(payload: str) -> Any:
    return _from_jsonable(json.loads(payload))


def _require_sqlite_database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError(
            "non-local persistence currently supports sqlite:/// database URLs"
        )
    raw_path = database_url.removeprefix("sqlite:///")
    if not raw_path:
        raise ValueError("sqlite database url must include a filesystem path")
    return Path(raw_path)


def _coerce_audit_metadata(audit_metadata: AuditMetadata | None) -> AuditMetadata:
    return AuditMetadata() if audit_metadata is None else audit_metadata


def _terminal_error_category(status: ExecutionStatus) -> ErrorCategory | None:
    if status is ExecutionStatus.TIMED_OUT:
        return ErrorCategory.TIMEOUT
    if status is ExecutionStatus.CANCELLED:
        return ErrorCategory.CANCELLATION
    return None


def _job_lookup_key(tenant_id: TenantId, job_id: JobId) -> tuple[str, str]:
    if job_id.tenant_id != tenant_id:
        raise ValueError("job id tenant must match lookup tenant")
    return (tenant_id.value, job_id.value)


def _request_lookup_key(tenant_id: TenantId, request_id: RequestId) -> tuple[str, str]:
    if request_id.tenant_id != tenant_id:
        raise ValueError("request id tenant must match lookup tenant")
    return (tenant_id.value, request_id.value)


def _migration_files() -> tuple[str, ...]:
    files = resources.files(_MIGRATIONS_PACKAGE)
    names = sorted(
        entry.name for entry in files.iterdir() if entry.name.endswith(".sql")
    )
    return tuple(names)


@dataclass(slots=True)
class SqlitePersistenceStore:
    """Small lazy-initialized SQLite store with migration tracking."""

    database_url: str
    _database_path: Path = field(init=False)
    _initialized: bool = False
    _init_lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        self._database_path = _require_sqlite_database_path(self.database_url)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_initialized()
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                applied = {
                    cast(str, row["version"])
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                }
                for migration_name in _migration_files():
                    if migration_name in applied:
                        continue
                    migration_sql = (
                        resources.files(_MIGRATIONS_PACKAGE)
                        .joinpath(migration_name)
                        .read_text(encoding="utf-8")
                    )
                    connection.executescript(migration_sql)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                        (migration_name, datetime.now(UTC).isoformat()),
                    )
                connection.commit()
            self._initialized = True


@dataclass(slots=True)
class SqliteJobRepository(Generic[RequestPayloadT, ResultPayloadT]):
    """Durable tenant-scoped job repository stored in SQLite tables."""

    database_url: str
    store: SqlitePersistenceStore = field(init=False)

    def __post_init__(self) -> None:
        self.store = SqlitePersistenceStore(self.database_url)

    def create(
        self, request: ExecutionRequest[RequestPayloadT]
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        record: JobRecord[RequestPayloadT, ResultPayloadT] = JobRecord(
            tenant_id=request.tenant_id,
            request=request,
            state=ExecutionState(
                tenant_id=request.tenant_id,
                request_id=request.request_id,
                job_id=request.job_id,
                status=ExecutionStatus.RECEIVED,
                submitted_at=request.submitted_at,
                updated_at=request.submitted_at,
            ),
        )
        with self.store.transaction() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO jobs(
                        tenant_id, job_id, request_id, idempotency_key, status,
                        submitted_at, updated_at, started_at, finished_at, record_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.tenant_id.value,
                        request.job_id.value,
                        request.request_id.value,
                        request.idempotency_key.value,
                        record.state.status.value,
                        request.submitted_at.isoformat(),
                        request.submitted_at.isoformat(),
                        None,
                        None,
                        _encode_record(record),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "jobs.tenant_id, jobs.job_id" in message:
                    raise ValueError("job already exists for tenant") from exc
                if "jobs.tenant_id, jobs.request_id" in message:
                    raise ValueError("request already exists for tenant") from exc
                raise
            self._append_audit_event(
                connection,
                tenant_id=request.tenant_id,
                request_id=request.request_id,
                job_id=request.job_id,
                event_type="job_created",
                recorded_at=request.submitted_at,
                to_status=ExecutionStatus.RECEIVED,
            )
        return record

    def get(
        self, tenant_id: TenantId, job_id: JobId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        tenant_key, job_key = _job_lookup_key(tenant_id, job_id)
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM jobs WHERE tenant_id = ? AND job_id = ?",
                (tenant_key, job_key),
            ).fetchone()
        if row is None:
            raise KeyError(f"job not found for tenant: {job_id.value}")
        return cast(
            JobRecord[RequestPayloadT, ResultPayloadT],
            _decode_record(cast(str, row["record_json"])),
        )

    def get_by_request_id(
        self, tenant_id: TenantId, request_id: RequestId
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        tenant_key, request_key = _request_lookup_key(tenant_id, request_id)
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM jobs WHERE tenant_id = ? AND request_id = ?",
                (tenant_key, request_key),
            ).fetchone()
        if row is None:
            raise KeyError(f"request not found for tenant: {request_id.value}")
        return cast(
            JobRecord[RequestPayloadT, ResultPayloadT],
            _decode_record(cast(str, row["record_json"])),
        )

    def find_by_idempotency_key(
        self, tenant_id: TenantId, idempotency_key: IdempotencyKey
    ) -> IdempotencyRecord | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM idempotency_records WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id.value, idempotency_key.value),
            ).fetchone()
        if row is None:
            return None
        return cast(IdempotencyRecord, _decode_record(cast(str, row["record_json"])))

    def reserve_idempotency(
        self,
        tenant_id: TenantId,
        idempotency_key: IdempotencyKey,
        request_id: RequestId,
        job_id: JobId,
        *,
        created_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> IdempotencyRecord:
        _ = _request_lookup_key(tenant_id, request_id)
        _ = _job_lookup_key(tenant_id, job_id)
        record = IdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            job_id=job_id,
            created_at=created_at or datetime.now(UTC),
        )
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM idempotency_records WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id.value, idempotency_key.value),
            ).fetchone()
            if existing is not None:
                restored = cast(
                    IdempotencyRecord,
                    _decode_record(cast(str, existing["record_json"])),
                )
                if restored.request_id != request_id or restored.job_id != job_id:
                    raise ValueError(
                        "idempotency key is already reserved for a different job"
                    )
                return restored
            connection.execute(
                """
                INSERT INTO idempotency_records(
                    tenant_id, idempotency_key, request_id, job_id, created_at, record_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id.value,
                    idempotency_key.value,
                    request_id.value,
                    job_id.value,
                    record.created_at.isoformat(),
                    _encode_record(record),
                ),
            )
            self._append_audit_event(
                connection,
                tenant_id=tenant_id,
                request_id=request_id,
                job_id=job_id,
                event_type="idempotency_reserved",
                recorded_at=record.created_at,
                audit_metadata=_coerce_audit_metadata(audit_metadata),
                metadata=(("idempotency_key", idempotency_key.value),),
            )
        return record

    def mark_validated(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.VALIDATED,
            updated_at=updated_at,
            audit_metadata=audit_metadata,
        )

    def mark_queued(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.QUEUED,
            updated_at=updated_at,
            audit_metadata=audit_metadata,
        )

    def mark_starting(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        started_at: datetime,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.STARTING,
            updated_at=updated_at or started_at,
            started_at=started_at,
            audit_metadata=audit_metadata,
        )

    def mark_running(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.RUNNING,
            updated_at=updated_at,
            timeout_state=TimeoutState.ACTIVE,
            audit_metadata=audit_metadata,
        )

    def request_cancellation(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        updated_at: datetime | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_non_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.CANCELLING,
            updated_at=updated_at,
            cancellation_state=CancellationState.REQUESTED,
            audit_metadata=audit_metadata,
        )

    def mark_succeeded(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        payload: ResultPayloadT | None = None,
        summary: ResultSummary | None = None,
        artifacts: tuple[ArtifactSummary, ...] = (),
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.SUCCEEDED,
            finished_at=finished_at,
            payload=payload,
            summary=summary,
            artifacts=artifacts,
            timeout_state=TimeoutState.CLEARED,
            audit_metadata=audit_metadata,
        )

    def mark_failed(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.FAILED,
            finished_at=finished_at,
            error=error,
            summary=summary,
            audit_metadata=audit_metadata,
        )

    def mark_timed_out(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.TIMED_OUT,
            finished_at=finished_at,
            error=error,
            summary=summary,
            timeout_state=TimeoutState.EXCEEDED,
            audit_metadata=audit_metadata,
        )

    def mark_cancelled(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        finished_at: datetime,
        error: ErrorDetails,
        summary: ResultSummary | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        return self._transition_terminal(
            tenant_id,
            job_id,
            status=ExecutionStatus.CANCELLED,
            finished_at=finished_at,
            error=error,
            summary=summary,
            cancellation_state=CancellationState.COMPLETED,
            audit_metadata=audit_metadata,
        )

    def list_audit_events(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[AuditEvent, ...]:
        tenant_key, job_key = _job_lookup_key(tenant_id, job_id)
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM audit_events WHERE tenant_id = ? AND job_id = ? ORDER BY sequence ASC",
                (tenant_key, job_key),
            ).fetchall()
        return tuple(
            cast(AuditEvent, _decode_record(cast(str, row["event_json"])))
            for row in rows
        )

    def _transition_non_terminal(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        status: ExecutionStatus,
        updated_at: datetime | None,
        started_at: datetime | None = None,
        cancellation_state: CancellationState | None = None,
        timeout_state: TimeoutState | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        tenant_key, job_key = _job_lookup_key(tenant_id, job_id)
        with self.store.transaction() as connection:
            record = self._get_locked_record(connection, tenant_key, job_key, job_id)
            previous_state = record.state
            next_state = record.state.transition_to(
                status,
                updated_at=updated_at,
                started_at=started_at,
                cancellation_state=cancellation_state,
                timeout_state=timeout_state,
            )
            updated_record = replace(record, state=next_state, result=None)
            self._store_record(connection, updated_record)
            self._append_audit_event(
                connection,
                tenant_id=tenant_id,
                request_id=record.request.request_id,
                job_id=job_id,
                event_type="job_status_changed",
                recorded_at=next_state.updated_at,
                audit_metadata=_coerce_audit_metadata(audit_metadata),
                from_status=previous_state.status,
                to_status=next_state.status,
                summary=next_state.summary,
                error=next_state.error,
            )
            return updated_record

    def _transition_terminal(
        self,
        tenant_id: TenantId,
        job_id: JobId,
        *,
        status: ExecutionStatus,
        finished_at: datetime,
        payload: ResultPayloadT | None = None,
        summary: ResultSummary | None = None,
        artifacts: tuple[ArtifactSummary, ...] = (),
        error: ErrorDetails | None = None,
        cancellation_state: CancellationState | None = None,
        timeout_state: TimeoutState | None = None,
        audit_metadata: AuditMetadata | None = None,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        required_category = _terminal_error_category(status)
        if status is ExecutionStatus.SUCCEEDED and error is not None:
            raise ValueError("successful executions must not include an error")
        if status is not ExecutionStatus.SUCCEEDED and error is None:
            raise ValueError(f"{status.value} executions must include an error")
        if (
            required_category is not None
            and error is not None
            and error.category is not required_category
        ):
            raise ValueError(
                f"{status.value} executions must use matching error details"
            )
        tenant_key, job_key = _job_lookup_key(tenant_id, job_id)
        with self.store.transaction() as connection:
            record = self._get_locked_record(connection, tenant_key, job_key, job_id)
            previous_state = record.state
            next_state = record.state.transition_to(
                status,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_state=cancellation_state,
                timeout_state=timeout_state,
                summary=summary,
                error=error,
            )
            result = ExecutionResult(
                tenant_id=record.tenant_id,
                request_id=record.request.request_id,
                job_id=record.request.job_id,
                status=status,
                completed_at=finished_at,
                payload=payload,
                summary=summary,
                artifacts=artifacts,
                error=error,
            )
            updated_record = replace(record, state=next_state, result=result)
            self._store_record(connection, updated_record)
            self._append_audit_event(
                connection,
                tenant_id=tenant_id,
                request_id=record.request.request_id,
                job_id=job_id,
                event_type="job_status_changed",
                recorded_at=finished_at,
                audit_metadata=_coerce_audit_metadata(audit_metadata),
                from_status=previous_state.status,
                to_status=next_state.status,
                summary=summary,
                error=error,
                metadata=(("terminal", "true"),),
            )
            return updated_record

    def _get_locked_record(
        self,
        connection: sqlite3.Connection,
        tenant_key: str,
        job_key: str,
        job_id: JobId,
    ) -> JobRecord[RequestPayloadT, ResultPayloadT]:
        row = connection.execute(
            "SELECT record_json FROM jobs WHERE tenant_id = ? AND job_id = ?",
            (tenant_key, job_key),
        ).fetchone()
        if row is None:
            raise KeyError(f"job not found for tenant: {job_id.value}")
        return cast(
            JobRecord[RequestPayloadT, ResultPayloadT],
            _decode_record(cast(str, row["record_json"])),
        )

    def _store_record(
        self,
        connection: sqlite3.Connection,
        record: JobRecord[RequestPayloadT, ResultPayloadT],
    ) -> None:
        connection.execute(
            """
            UPDATE jobs
            SET request_id = ?, idempotency_key = ?, status = ?, submitted_at = ?,
                updated_at = ?, started_at = ?, finished_at = ?, record_json = ?
            WHERE tenant_id = ? AND job_id = ?
            """,
            (
                record.request.request_id.value,
                record.request.idempotency_key.value,
                record.state.status.value,
                record.request.submitted_at.isoformat(),
                record.state.updated_at.isoformat(),
                None
                if record.state.started_at is None
                else record.state.started_at.isoformat(),
                None
                if record.state.finished_at is None
                else record.state.finished_at.isoformat(),
                _encode_record(record),
                record.tenant_id.value,
                record.request.job_id.value,
            ),
        )

    def _append_audit_event(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: TenantId,
        request_id: RequestId,
        job_id: JobId,
        event_type: str,
        recorded_at: datetime,
        audit_metadata: AuditMetadata | None = None,
        from_status: ExecutionStatus | None = None,
        to_status: ExecutionStatus | None = None,
        summary: ResultSummary | None = None,
        error: ErrorDetails | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> AuditEvent:
        next_sequence = cast(
            int,
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM audit_events"
            ).fetchone()["next_sequence"],
        )
        event = AuditEvent(
            event_id=f"audit-{next_sequence:06d}",
            tenant_id=tenant_id,
            request_id=request_id,
            job_id=job_id,
            event_type=event_type,
            recorded_at=recorded_at,
            audit_metadata=_coerce_audit_metadata(audit_metadata),
            from_status=from_status,
            to_status=to_status,
            summary=summary,
            error=error,
            metadata=metadata,
        )
        connection.execute(
            """
            INSERT INTO audit_events(
                sequence, tenant_id, job_id, event_id, event_type,
                recorded_at, from_status, to_status, event_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_sequence,
                tenant_id.value,
                job_id.value,
                event.event_id,
                event.event_type,
                event.recorded_at.isoformat(),
                None if event.from_status is None else event.from_status.value,
                None if event.to_status is None else event.to_status.value,
                _encode_record(event),
            ),
        )
        return event


@dataclass(slots=True)
class SqliteArtifactMetadataRepository:
    """Durable artifact metadata repository stored separately from artifact bytes."""

    database_url: str
    store: SqlitePersistenceStore = field(init=False)

    def __post_init__(self) -> None:
        self.store = SqlitePersistenceStore(self.database_url)

    def put(self, record: ArtifactMetadataRecord) -> ArtifactMetadataRecord:
        with self.store.transaction() as connection:
            content_backend = None
            content_locator = None
            if record.content_ref is not None:
                content_backend = record.content_ref.storage_backend
                content_locator = record.content_ref.locator
            connection.execute(
                """
                INSERT INTO artifact_metadata(
                    tenant_id, job_id, artifact_key, created_at,
                    content_backend, content_locator, record_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, job_id, artifact_key) DO UPDATE SET
                    created_at = excluded.created_at,
                    content_backend = excluded.content_backend,
                    content_locator = excluded.content_locator,
                    record_json = excluded.record_json
                """,
                (
                    record.tenant_id.value,
                    record.job_id.value,
                    record.artifact.key,
                    record.created_at.isoformat(),
                    content_backend,
                    content_locator,
                    _encode_record(record),
                ),
            )
        return record

    def get(
        self, tenant_id: TenantId, job_id: JobId, artifact_key: str
    ) -> ArtifactMetadataRecord | None:
        _ = _job_lookup_key(tenant_id, job_id)
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM artifact_metadata WHERE tenant_id = ? AND job_id = ? AND artifact_key = ?",
                (tenant_id.value, job_id.value, artifact_key.strip()),
            ).fetchone()
        if row is None:
            return None
        return cast(
            ArtifactMetadataRecord,
            _decode_record(cast(str, row["record_json"])),
        )

    def list_for_job(
        self, tenant_id: TenantId, job_id: JobId
    ) -> tuple[ArtifactMetadataRecord, ...]:
        _ = _job_lookup_key(tenant_id, job_id)
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM artifact_metadata WHERE tenant_id = ? AND job_id = ? ORDER BY created_at ASC, artifact_key ASC",
                (tenant_id.value, job_id.value),
            ).fetchall()
        return tuple(
            cast(ArtifactMetadataRecord, _decode_record(cast(str, row["record_json"])))
            for row in rows
        )

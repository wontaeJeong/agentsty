CREATE TABLE IF NOT EXISTS jobs (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (tenant_id, request_id)
);

CREATE INDEX IF NOT EXISTS jobs_status_idx
    ON jobs (tenant_id, status, updated_at);

CREATE TABLE IF NOT EXISTS idempotency_records (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    event_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_events_job_idx
    ON audit_events (tenant_id, job_id, sequence);

CREATE TABLE IF NOT EXISTS artifact_metadata (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    artifact_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    content_backend TEXT,
    content_locator TEXT,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id, artifact_key)
);

CREATE INDEX IF NOT EXISTS artifact_metadata_job_idx
    ON artifact_metadata (tenant_id, job_id, created_at, artifact_key);

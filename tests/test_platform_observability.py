from __future__ import annotations

import importlib
import json
import logging
from typing import Any


def _observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def test_structured_logging_redacts_sensitive_fields_and_carries_correlation() -> None:
    observability = _observability_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-123")
    job_id = domain.JobId(tenant_id=tenant, value="job-456")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        metadata=(("component", "gateway"),),
    )

    logger = observability.StructuredLogger(service_name="agentsty-platform")
    event = logger.event(
        "request.accepted",
        "Accepted execution request",
        trace_context=trace_context,
        attributes={
            "tenant_label": "gold",
            "api_key": "secret-value",
            "nested": {"authorization": "Bearer secret", "safe": True},
        },
        metadata=(("path", "/v1/chat/completions"),),
    )
    payload = event.to_payload()

    assert payload["tenant_id"] == "tenant-a"
    assert payload["request_id"] == "req-123"
    assert payload["job_id"] == "job-456"
    assert payload["correlation_id"] == trace_context.correlation_id
    assert payload["attributes"] == {
        "tenant_label": "gold",
        "api_key": "[REDACTED]",
        "nested": {"authorization": "[REDACTED]", "safe": True},
    }
    assert payload["metadata"] == {"path": "/v1/chat/completions"}


def test_structured_logger_emit_writes_json_payload(caplog: Any) -> None:
    observability = _observability_module()

    caplog.set_level(logging.INFO, logger="agentsty.test")
    structured_logger = observability.StructuredLogger(
        service_name="agentsty-platform",
        logger_name="agentsty.test",
    )

    event = structured_logger.emit(
        "health.checked",
        "Health was evaluated",
        severity=observability.LogSeverity.INFO,
        attributes={"token": "sensitive"},
    )

    assert event.severity is observability.LogSeverity.INFO
    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "health.checked"
    assert payload["attributes"]["token"] == "[REDACTED]"


def test_metric_recorder_tracks_counter_and_duration_with_trace_context() -> None:
    observability = _observability_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
    )
    recorder = observability.MetricRecorder()

    counter = recorder.increment_counter(
        "requests_total",
        attributes={"component": "gateway"},
        trace_context=trace_context,
    )
    duration = recorder.record_duration(
        "request_latency",
        1.25,
        attributes={"component": "gateway"},
        trace_context=trace_context,
    )

    assert counter.kind is observability.MetricKind.COUNTER
    assert counter.to_payload()["request_id"] == "req-1"
    assert duration.kind is observability.MetricKind.HISTOGRAM
    assert duration.unit == "seconds"
    assert len(recorder.snapshot()) == 2


def test_trace_context_attachment_propagates_to_logging_and_metrics() -> None:
    observability = _observability_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-99")
    job_id = domain.JobId(tenant_id=tenant, value="job-99")
    trace_context = observability.TraceContext.new(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
    )

    logger = observability.StructuredLogger(service_name="agentsty-platform")
    recorder = observability.MetricRecorder()

    with observability.attach_trace_context(trace_context):
        event = logger.event("job.started", "Job execution started")
        point = recorder.increment_counter("jobs_started_total")
        current = observability.current_trace_context()

    assert current == trace_context
    assert event.trace_context == trace_context
    assert point.trace_context == trace_context
    assert observability.current_trace_context() is None


def test_health_and_readiness_reports_aggregate_component_state() -> None:
    observability = _observability_module()

    health = observability.HealthReport.from_components(
        "agentsty-platform",
        (
            observability.HealthComponent(
                name="gateway",
                status=observability.HealthStatus.HEALTHY,
            ),
            observability.HealthComponent(
                name="artifact-store",
                status=observability.HealthStatus.DEGRADED,
                detail="latency elevated",
            ),
        ),
    )
    readiness = observability.ReadinessReport.from_checks(
        "agentsty-platform",
        (
            observability.ReadinessCheck(name="config-loaded", ready=True),
            observability.ReadinessCheck(name="job-repository", ready=False),
            observability.ReadinessCheck(
                name="metrics-exporter",
                ready=False,
                requirement=observability.ReadinessRequirement.OPTIONAL,
            ),
        ),
    )

    assert health.status is observability.HealthStatus.DEGRADED
    assert readiness.ready is False
    assert readiness.blocking_checks == ("job-repository",)

from __future__ import annotations

import importlib

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.runtime_opencode_support import FakeCommandRunner


def _api_package() -> Any:
    return importlib.import_module("agentsty_api")


def _api_dependencies_module() -> Any:
    return importlib.import_module("agentsty_api.dependencies")


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _api_auth_module() -> Any:
    return importlib.import_module("agentsty_api.auth")


def _persistence_module() -> Any:
    return importlib.import_module("agentsty_platform.persistence")


def _runtimes_module() -> Any:
    return importlib.import_module("agentsty_platform.runtimes")


def _services_module() -> Any:
    return importlib.import_module("agentsty_platform.services")


def _runtime_package() -> Any:
    return importlib.import_module("agentsty_runtime_opencode")


def _local_settings(tmp_path: Path) -> Any:
    config = _config_module()
    return config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={
            "runtime": {"workspace_root": tmp_path / "runtime"},
        },
    )


def _dev_settings(tmp_path: Path) -> Any:
    config = _config_module()
    return config.PlatformSettings.for_profile(
        config.EnvironmentProfile.DEV,
        overrides={
            "runtime": {"workspace_root": tmp_path / "runtime"},
        },
    )


def _execution_template() -> Any:
    api_dependencies = _api_dependencies_module()
    executors = _executors_module()
    localdev = importlib.import_module("agentsty_platform.localdev")
    return api_dependencies.ExecutionTemplate(
        sandbox_program=localdev.build_local_runner_program(
            environment=(("AGENTSTY_RUNNER_COMMAND_RUNNER", "inline"),)
        ),
        sandbox_resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=128,
        ),
        desired_isolation=executors.SandboxIsolationMode.PROCESS,
    )


def _build_api_dependencies(tmp_path: Path) -> Any:
    api_dependencies = _api_dependencies_module()
    gateway = _gateway_module()
    persistence = _persistence_module()
    services = _services_module()
    runtime_pkg = _runtime_package()
    localdev = importlib.import_module("agentsty_platform.localdev")

    settings = _local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=gateway.LocalGatewayTransport(),
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_pkg.OpenCodeRuntimeAdapter(
            gateway_client=gateway_client,
            runtime_settings=settings.runtime,
            command_runner=FakeCommandRunner(),
        ),
        sandbox_executor=localdev.LocalProcessSandboxExecutor(
            executor_settings=settings.executor,
            workspace_root=settings.runtime.workspace_root,
        ),
        intake_service=services.RequestIntakeService(jobs=jobs),
    )
    return api_dependencies.APIDependencies(
        settings=settings,
        orchestrator=orchestrator,
        execution_template=_execution_template(),
        health_reporter=api_dependencies._DefaultHealthReporter(settings),
        readiness_reporter=api_dependencies._DefaultReadinessReporter(settings),
    )


def test_create_chat_completion_returns_openai_style_payload(tmp_path: Path) -> None:
    api = _api_package()
    app = api.create_app(_build_api_dependencies(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "request_id": "req-api-1",
            "idempotency_key": "idem-api-1",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello api"}],
            "request_timeout_seconds": 30,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["request_id"] == "req-api-1"
    assert payload["choices"][0]["message"]["content"].startswith(
        "local gateway echo: hello api"
    )
    assert payload["usage"]["total_tokens"] > 0
    assert payload["summary"]["artifact_count"] == 1
    assert payload["artifacts"][0]["key"] == "opencode/session-export.json"
    assert payload["artifacts"][0]["media_type"] == "application/json"
    assert payload["artifacts"][0]["storage"] is None


@dataclass(slots=True)
class DeferredRuntimeAdapter:
    runtime_name: str = "deferred-runtime"
    _sessions: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def capabilities(self) -> Any:
        return _runtimes_module().RuntimeCapabilities()

    def prepare(self, request: Any) -> Any:
        runtimes = _runtimes_module()
        session = runtimes.RuntimeSession(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            runtime_name=self.runtime_name,
            session_id=f"deferred-{request.job_id.value}",
            workspace_path=request.workspace_path,
            trace_context=request.trace_context,
            metadata=request.metadata,
        )
        self._sessions[session.session_id] = {"session": session, "result": None}
        return session

    def invoke(self, session: Any, request: Any) -> Any:
        return _runtimes_module().RuntimeInvocationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            metadata=request.metadata,
        )

    def collect_result(self, session: Any, request: Any | None = None) -> Any:
        stored = self._sessions[session.session_id]["result"]
        return _runtimes_module().RuntimeCollectionResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            ready=stored is not None,
            result=stored,
            metadata=() if request is None else request.metadata,
        )

    def request_cancellation(self, session: Any, request: Any) -> Any:
        domain = _domain_module()
        runtimes = _runtimes_module()
        self._sessions[session.session_id]["result"] = domain.ExecutionResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            status=domain.ExecutionStatus.CANCELLED,
            completed_at=request.requested_at,
            summary=domain.ResultSummary(duration_seconds=0.0),
            error=domain.CancellationError(
                request.reason or "cancelled by operator"
            ).as_details(),
        )
        return runtimes.RuntimeCancellationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            acknowledged=True,
            requested_at=request.requested_at,
            metadata=request.metadata,
        )

    def cleanup(self, session: Any, request: Any | None = None) -> Any:
        runtimes = _runtimes_module()
        del self._sessions[session.session_id]
        return runtimes.RuntimeCleanupResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            cleaned=True,
            released_paths=(str(session.workspace_path),),
            metadata=() if request is None else request.metadata,
        )


@dataclass(slots=True)
class DeferredSandboxExecutor:
    executor_name: str = "deferred-executor"
    _sandboxes: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def capabilities(self) -> Any:
        executors = _executors_module()
        return executors.SandboxCapabilities(
            supported_isolation_modes=(executors.SandboxIsolationMode.CONTAINER,),
            tenant_boundary_kind="namespace",
            supports_status_inspection=True,
            supports_cancellation=True,
            supports_cleanup=True,
            supports_separate_launch_phase=True,
        )

    def create(self, request: Any) -> Any:
        executors = _executors_module()
        boundary = executors.TenantResourceBoundary(
            tenant_id=request.tenant_id,
            boundary_kind="namespace",
            boundary_name=f"tenant-{request.tenant_id.value}",
        )
        identity = executors.SandboxResourceIdentity(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            executor_name=self.executor_name,
            provider="local",
            resource_kind="job",
            resource_name=f"sandbox-{request.job_id.value}",
            boundary=boundary,
        )
        sandbox = executors.SandboxHandle(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            executor_name=self.executor_name,
            identity=identity,
            program=request.program,
            resources=request.resources,
            timeouts=request.timeouts,
            desired_isolation=request.desired_isolation,
            metadata=request.metadata,
        )
        self._sandboxes[sandbox.identity.resource_name] = {
            "sandbox": sandbox,
            "status": executors.SandboxStatus.RUNNING,
            "started_at": datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
            "finished_at": None,
            "cancelled_at": None,
        }
        return sandbox

    def launch(self, sandbox: Any, request: Any | None = None) -> Any:
        executors = _executors_module()
        started_at = self._sandboxes[sandbox.identity.resource_name]["started_at"]
        return executors.SandboxLaunchReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            accepted_at=started_at,
            deadline_at=started_at,
            metadata=() if request is None else request.metadata,
        )

    def inspect(self, sandbox: Any) -> Any:
        executors = _executors_module()
        state = self._sandboxes[sandbox.identity.resource_name]
        return executors.SandboxInspection(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            status=state["status"],
            observed_at=state["started_at"],
            started_at=state["started_at"],
            finished_at=state["finished_at"],
            cancellation_requested_at=state["cancelled_at"],
        )

    def request_cancellation(self, sandbox: Any, request: Any) -> Any:
        executors = _executors_module()
        state = self._sandboxes[sandbox.identity.resource_name]
        state["status"] = executors.SandboxStatus.CANCELLED
        state["cancelled_at"] = request.requested_at
        state["finished_at"] = request.requested_at
        return executors.SandboxCancellationReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            acknowledged=True,
            requested_at=request.requested_at,
            metadata=request.metadata,
        )

    def cleanup(self, sandbox: Any, request: Any | None = None) -> Any:
        executors = _executors_module()
        del self._sandboxes[sandbox.identity.resource_name]
        return executors.SandboxCleanupResult(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            cleaned=True,
            cleaned_at=datetime(2026, 4, 16, 12, 5, tzinfo=UTC),
            released_resources=(sandbox.identity.resource_name,),
            metadata=() if request is None else request.metadata,
        )


def _build_deferred_dependencies(tmp_path: Path) -> Any:
    api_dependencies = _api_dependencies_module()
    persistence = _persistence_module()
    services = _services_module()

    settings = _local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    policy_service = services.InMemoryPolicyQuotaService(
        max_active_executions_per_tenant=1
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=DeferredRuntimeAdapter(),
        sandbox_executor=DeferredSandboxExecutor(),
        intake_service=services.RequestIntakeService(jobs=jobs),
        policy_service=policy_service,
    )
    return api_dependencies.APIDependencies(
        settings=settings,
        orchestrator=orchestrator,
        execution_template=_execution_template(),
        health_reporter=api_dependencies._DefaultHealthReporter(settings),
        readiness_reporter=api_dependencies._DefaultReadinessReporter(settings),
    )


@dataclass(slots=True)
class StubPrincipalVerifier:
    authorized_tenant_ids: tuple[str, ...]
    subject: str = "user-123"
    issuer: str = "https://auth.dev.internal"
    audience: str = "agentsty-api"

    def verify_bearer_token(self, token: str, *, settings: Any) -> Any:
        assert token == "stub-token"
        return _api_auth_module().AuthenticatedPrincipal(
            subject=self.subject,
            issuer=self.issuer,
            audience=self.audience,
            authorized_tenant_ids=self.authorized_tenant_ids,
            claims={
                "sub": self.subject,
                "iss": settings.auth.issuer,
                "aud": settings.auth.audience,
                "tenant_ids": list(self.authorized_tenant_ids),
            },
        )


def _build_authenticated_dependencies(
    tmp_path: Path, *, authorized_tenant_ids: tuple[str, ...]
) -> Any:
    api_dependencies = _api_dependencies_module()
    persistence = _persistence_module()
    services = _services_module()

    settings = _dev_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    policy_service = services.InMemoryPolicyQuotaService(
        max_active_executions_per_tenant=1
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=DeferredRuntimeAdapter(),
        sandbox_executor=DeferredSandboxExecutor(),
        intake_service=services.RequestIntakeService(jobs=jobs),
        policy_service=policy_service,
    )
    return api_dependencies.APIDependencies(
        settings=settings,
        orchestrator=orchestrator,
        execution_template=_execution_template(),
        health_reporter=api_dependencies._DefaultHealthReporter(settings),
        readiness_reporter=api_dependencies._DefaultReadinessReporter(settings),
        principal_verifier=StubPrincipalVerifier(authorized_tenant_ids),
    )


def _advance_deferred_job_to_succeeded(
    dependencies: Any, *, tenant_id: str, job_id: str
) -> None:
    domain = _domain_module()
    gateway = _gateway_module()
    tenant = domain.TenantId(tenant_id)
    job = domain.JobId(tenant_id=tenant, value=job_id)
    record = dependencies.orchestrator.jobs.get(tenant, job)
    runtime_adapter = dependencies.orchestrator.runtime_adapter
    prompt = record.request.payload.messages[0].content
    runtime_adapter._sessions[f"deferred-{job_id}"]["result"] = domain.ExecutionResult(
        tenant_id=record.tenant_id,
        request_id=record.request.request_id,
        job_id=record.request.job_id,
        status=domain.ExecutionStatus.SUCCEEDED,
        completed_at=(record.state.started_at or record.request.submitted_at)
        + timedelta(seconds=1),
        payload=gateway.GatewayResponse(
            tenant_id=record.tenant_id,
            target=record.request.payload.target,
            message=gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.ASSISTANT,
                content=f"deferred gateway echo: {prompt}",
            ),
            finish_reason=gateway.GatewayFinishReason.STOP,
            usage=gateway.GatewayUsage(input_tokens=1, output_tokens=1),
        ),
        summary=domain.ResultSummary(duration_seconds=0.0),
    )


def test_status_and_cancellation_routes_wrap_shared_orchestrator(
    tmp_path: Path,
) -> None:
    api = _api_package()
    dependencies = _build_deferred_dependencies(tmp_path)
    app = api.create_app(dependencies)
    client = TestClient(app)

    submit = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-running",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold"}],
        },
    )

    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    _advance_deferred_job_to_succeeded(
        dependencies, tenant_id="tenant-a", job_id=job_id
    )

    status_response = client.get(
        f"/v1/chat/completions/{job_id}",
        headers={"X-Agentsty-Tenant-Id": "tenant-a"},
    )
    cancel_submit = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-cancel",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold"}],
        },
    )
    cancel_job_id = cancel_submit.json()["job_id"]
    cancel_response = client.post(
        f"/v1/chat/completions/{cancel_job_id}/cancel",
        headers={
            "X-Agentsty-Tenant-Id": "tenant-a",
            "X-Agentsty-Cancel-Reason": "operator stop",
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["choices"][0]["message"]["content"].startswith(
        "deferred gateway echo:"
    )
    assert cancel_response.status_code == 202
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["cancellation_requested"] is True


def test_quota_failures_are_mapped_to_http_errors(tmp_path: Path) -> None:
    api = _api_package()
    app = api.create_app(_build_deferred_dependencies(tmp_path))
    client = TestClient(app)

    first = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-first",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold"}],
        },
    )
    second = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-a",
            "idempotency_key": "idem-second",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "blocked"}],
        },
    )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["error"]["category"] == "quota_exceeded"


def test_health_and_readiness_endpoints_use_shared_observability_models(
    tmp_path: Path,
) -> None:
    api = _api_package()
    app = api.create_app(_build_api_dependencies(tmp_path))
    client = TestClient(app)

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert ready.status_code == 200
    assert ready.json()["ready"] is True


def test_non_local_profile_requires_bearer_authentication(tmp_path: Path) -> None:
    api = _api_package()
    app = api.create_app(
        _build_authenticated_dependencies(
            tmp_path, authorized_tenant_ids=("tenant-auth",)
        )
    )
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "tenant_id": "tenant-auth",
            "idempotency_key": "idem-auth-required",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello auth"}],
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["category"] == "authentication"


def test_non_local_profile_rejects_tenant_outside_verified_principal_scope(
    tmp_path: Path,
) -> None:
    api = _api_package()
    app = api.create_app(
        _build_authenticated_dependencies(
            tmp_path, authorized_tenant_ids=("tenant-allowed",)
        )
    )
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer stub-token"},
        json={
            "tenant_id": "tenant-denied",
            "idempotency_key": "idem-authz",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "wrong tenant"}],
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["category"] == "authorization"
    assert body["error"]["metadata"]["requested_tenant_id"] == "tenant-denied"


def test_non_local_status_and_cancel_use_authenticated_tenant_binding(
    tmp_path: Path,
) -> None:
    api = _api_package()
    dependencies = _build_authenticated_dependencies(
        tmp_path, authorized_tenant_ids=("tenant-auth",)
    )
    app = api.create_app(dependencies)
    client = TestClient(app)

    submit = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer stub-token"},
        json={
            "tenant_id": "tenant-auth",
            "idempotency_key": "idem-auth-status",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold authenticated"}],
        },
    )

    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    _advance_deferred_job_to_succeeded(
        dependencies, tenant_id="tenant-auth", job_id=job_id
    )

    status_response = client.get(
        f"/v1/chat/completions/{job_id}",
        headers={"Authorization": "Bearer stub-token"},
    )
    cancel_submit = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer stub-token"},
        json={
            "tenant_id": "tenant-auth",
            "idempotency_key": "idem-auth-cancel",
            "provider": "internal-openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hold authenticated"}],
        },
    )
    cancel_job_id = cancel_submit.json()["job_id"]
    cancel_response = client.post(
        f"/v1/chat/completions/{cancel_job_id}/cancel",
        headers={
            "Authorization": "Bearer stub-token",
            "X-Agentsty-Cancel-Reason": "operator stop",
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["tenant_id"] == "tenant-auth"
    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["choices"][0]["message"]["content"].startswith(
        "deferred gateway echo:"
    )
    assert cancel_response.status_code == 202
    assert cancel_response.json()["tenant_id"] == "tenant-auth"
    assert cancel_response.json()["status"] == "cancelled"

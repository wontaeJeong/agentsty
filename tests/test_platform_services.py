from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.runtime_opencode_support import FakeCommandRunner


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


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


def _build_submit_request(
    settings: Any,
    tenant: Any,
    *,
    key: str,
    prompt: str,
    program_environment: tuple[tuple[str, str], ...] = (),
) -> Any:
    gateway = _gateway_module()
    executors = _executors_module()
    services = _services_module()
    domain = _domain_module()
    localdev = importlib.import_module("agentsty_platform.localdev")
    trace_context = _observability_module().TraceContext.new(tenant_id=tenant)
    return services.ExecutionSubmitRequest(
        tenant_id=tenant,
        idempotency_key=domain.IdempotencyKey(key),
        gateway_request=gateway.GatewayRequest(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(
                provider="internal-openai",
                model="gpt-4o-mini",
            ),
            messages=(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.USER,
                    content=prompt,
                ),
            ),
            trace_context=trace_context,
            allowlist=gateway.GatewayAllowlist(
                allowed_providers=("internal-openai",),
                allowed_models=("gpt-4o-mini",),
            ),
        ),
        sandbox_program=localdev.build_local_runner_program(
            environment=(
                ("AGENTSTY_RUNNER_COMMAND_RUNNER", "inline"),
                *program_environment,
            )
        ),
        sandbox_resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=128,
        ),
        desired_isolation=executors.SandboxIsolationMode.PROCESS,
        trace_context=trace_context,
    )


def test_execution_orchestrator_happy_path_and_idempotent_replay(
    tmp_path: Path,
) -> None:
    domain = _domain_module()
    gateway = _gateway_module()
    persistence = _persistence_module()
    services = _services_module()
    runtime_pkg = _runtime_package()
    localdev = importlib.import_module("agentsty_platform.localdev")

    settings = _local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    transport = gateway.LocalGatewayTransport()
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=transport,
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )
    runtime_adapter = runtime_pkg.OpenCodeRuntimeAdapter(
        gateway_client=gateway_client,
        runtime_settings=settings.runtime,
        command_runner=FakeCommandRunner(),
    )
    sandbox_executor = localdev.LocalProcessSandboxExecutor(
        executor_settings=settings.executor,
        workspace_root=settings.runtime.workspace_root,
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_adapter,
        sandbox_executor=sandbox_executor,
        intake_service=services.RequestIntakeService(jobs=jobs),
    )
    tenant = domain.TenantId("tenant-a")
    submit_request = _build_submit_request(
        settings,
        tenant,
        key="idem-happy",
        prompt="hello orchestrator",
    )

    first = orchestrator.submit(submit_request)
    second = orchestrator.submit(submit_request)

    assert first.job.state.status is domain.ExecutionStatus.SUCCEEDED
    assert first.job.result is not None
    assert first.job.result.payload is not None
    assert first.job.result.payload.message.content.startswith(
        "local gateway echo: hello orchestrator"
    )
    assert first.cleanup_performed is True
    assert second.idempotent_replay is True
    assert second.job.request.job_id == first.job.request.job_id
    artifacts = artifact_metadata.list_for_job(tenant, first.job.request.job_id)
    assert len(artifacts) == 1
    assert artifacts[0].artifact.key == "opencode/session-export.json"
    assert artifacts[0].content_ref is None
    assert runtime_adapter.command_runner.run_calls == []
    assert runtime_adapter.command_runner.export_calls == []


def test_execution_orchestrator_maps_runtime_failure_to_shared_taxonomy(
    tmp_path: Path,
) -> None:
    domain = _domain_module()
    gateway = _gateway_module()
    persistence = _persistence_module()
    services = _services_module()
    runtime_pkg = _runtime_package()
    localdev = importlib.import_module("agentsty_platform.localdev")

    settings = _local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    transport = gateway.LocalGatewayTransport(
        scripted_outcomes=[
            gateway.GatewayFailure(
                gateway.GatewayFailureKind.UNAVAILABLE,
                "gateway unavailable",
            )
        ]
    )
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=transport,
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )
    runtime_adapter = runtime_pkg.OpenCodeRuntimeAdapter(
        gateway_client=gateway_client,
        runtime_settings=settings.runtime,
        command_runner=FakeCommandRunner(
            run_error=domain.GatewayError(
                "gateway unavailable",
                retryable=True,
                metadata=(("failure_kind", "unavailable"),),
            )
        ),
    )
    sandbox_executor = localdev.LocalProcessSandboxExecutor(
        executor_settings=settings.executor,
        workspace_root=settings.runtime.workspace_root,
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_adapter,
        sandbox_executor=sandbox_executor,
        intake_service=services.RequestIntakeService(jobs=jobs),
    )
    tenant = domain.TenantId("tenant-a")

    result = orchestrator.submit(
        _build_submit_request(
            settings,
            tenant,
            key="idem-fail",
            prompt="fail me",
            program_environment=(
                ("AGENTSTY_RUNNER_INLINE_ERROR_CATEGORY", "gateway_failure"),
                ("AGENTSTY_RUNNER_INLINE_ERROR_MESSAGE", "gateway unavailable"),
            ),
        )
    )

    assert result.job.state.status is domain.ExecutionStatus.FAILED
    assert result.job.result is not None
    assert result.job.result.error is not None
    assert result.job.result.error.category is domain.ErrorCategory.GATEWAY_FAILURE
    assert result.cleanup_performed is True


@dataclass(slots=True)
class DeferredRuntimeAdapter:
    runtime_name: str = "deferred-runtime"
    _sessions: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def capabilities(self) -> Any:
        runtimes = _runtimes_module()
        return runtimes.RuntimeCapabilities()

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
        runtimes = _runtimes_module()
        return runtimes.RuntimeInvocationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            metadata=request.metadata,
        )

    def collect_result(self, session: Any, request: Any | None = None) -> Any:
        runtimes = _runtimes_module()
        stored = self._sessions[session.session_id]["result"]
        return runtimes.RuntimeCollectionResult(
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
            "status": executors.SandboxStatus.CREATED,
            "started_at": None,
            "finished_at": None,
            "cancelled_at": None,
        }
        return sandbox

    def launch(self, sandbox: Any, request: Any | None = None) -> Any:
        executors = _executors_module()
        started_at = datetime(2026, 4, 16, 12, 0, tzinfo=UTC)
        state = self._sandboxes[sandbox.identity.resource_name]
        state["status"] = executors.SandboxStatus.RUNNING
        state["started_at"] = started_at
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
        domain = _domain_module()
        executors = _executors_module()
        state = self._sandboxes[sandbox.identity.resource_name]
        status = state["status"]
        if status is executors.SandboxStatus.CANCELLED:
            return executors.SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=status,
                observed_at=state["finished_at"],
                started_at=state["started_at"],
                finished_at=state["finished_at"],
                cancellation_requested_at=state["cancelled_at"],
                error=domain.CancellationError("cancelled by operator").as_details(),
            )
        return executors.SandboxInspection(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            status=status,
            observed_at=state["started_at"]
            or datetime(2026, 4, 16, 11, 59, tzinfo=UTC),
            started_at=state["started_at"],
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
        cleaned_at = datetime(2026, 4, 16, 12, 5, tzinfo=UTC)
        return executors.SandboxCleanupResult(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            cleaned=True,
            cleaned_at=cleaned_at,
            released_resources=(sandbox.identity.resource_name,),
            metadata=() if request is None else request.metadata,
        )


def test_execution_orchestrator_handles_cancellation_and_tenant_quota(
    tmp_path: Path,
) -> None:
    domain = _domain_module()
    persistence = _persistence_module()
    services = _services_module()

    settings = _local_settings(tmp_path)
    jobs = persistence.InMemoryJobRepository()
    artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
    runtime_adapter = DeferredRuntimeAdapter()
    sandbox_executor = DeferredSandboxExecutor()
    policy_service = services.InMemoryPolicyQuotaService(
        max_active_executions_per_tenant=1
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_adapter,
        sandbox_executor=sandbox_executor,
        intake_service=services.RequestIntakeService(jobs=jobs),
        policy_service=policy_service,
    )
    tenant = domain.TenantId("tenant-a")

    first = orchestrator.submit(
        _build_submit_request(settings, tenant, key="idem-running", prompt="hold")
    )
    second = orchestrator.submit(
        _build_submit_request(settings, tenant, key="idem-quota", prompt="blocked")
    )
    cancelled = orchestrator.cancel(
        services.ExecutionCancellationRequest(
            tenant_id=tenant,
            job_id=first.job.request.job_id,
            reason="operator stop",
        )
    )

    assert first.job.state.status is domain.ExecutionStatus.RUNNING
    assert second.job.state.status is domain.ExecutionStatus.FAILED
    assert second.job.result is not None
    assert second.job.result.error is not None
    assert second.job.result.error.category is domain.ErrorCategory.QUOTA_EXCEEDED
    assert cancelled.job.state.status is domain.ExecutionStatus.CANCELLED
    assert cancelled.job.result is not None
    assert cancelled.job.result.error is not None
    assert cancelled.job.result.error.category is domain.ErrorCategory.CANCELLATION
    assert cancelled.cleanup_performed is True

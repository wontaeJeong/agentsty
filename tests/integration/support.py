from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.runtime_opencode_support import FakeCommandRunner


def api_package() -> Any:
    return importlib.import_module("agentsty_api")


def api_dependencies_module() -> Any:
    return importlib.import_module("agentsty_api.dependencies")


def config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def observability_module() -> Any:
    return importlib.import_module("agentsty_platform.observability")


def persistence_module() -> Any:
    return importlib.import_module("agentsty_platform.persistence")


def runtimes_module() -> Any:
    return importlib.import_module("agentsty_platform.runtimes")


def services_module() -> Any:
    return importlib.import_module("agentsty_platform.services")


def runtime_package() -> Any:
    return importlib.import_module("agentsty_runtime_opencode")


def localdev_module() -> Any:
    return importlib.import_module("agentsty_platform.localdev")


def local_settings(tmp_path: Path) -> Any:
    config = config_module()
    return config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={"runtime": {"workspace_root": tmp_path / "runtime"}},
    )


def _next_inspect_call(state: dict[str, object]) -> int:
    count = state.get("inspect_calls", 0)
    if not isinstance(count, int):
        raise AssertionError("inspect_calls must remain an int")
    count += 1
    state["inspect_calls"] = count
    return count


def execution_template() -> Any:
    api_dependencies = api_dependencies_module()
    executors = executors_module()
    localdev = localdev_module()
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


def build_submit_request(settings: Any, tenant: Any, *, key: str, prompt: str) -> Any:
    gateway = gateway_module()
    executors = executors_module()
    services = services_module()
    domain = domain_module()
    localdev = localdev_module()
    trace_context = observability_module().TraceContext.new(tenant_id=tenant)
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
            environment=(("AGENTSTY_RUNNER_COMMAND_RUNNER", "inline"),)
        ),
        sandbox_resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=128,
        ),
        desired_isolation=executors.SandboxIsolationMode.PROCESS,
        trace_context=trace_context,
        timeouts=domain.ExecutionTimeouts(
            request_timeout_seconds=30,
            execution_timeout_seconds=settings.timeouts.execution_timeout_seconds,
            cancellation_grace_period_seconds=settings.timeouts.cancellation_grace_period_seconds,
        ),
    )


def build_local_api_dependencies(tmp_path: Path) -> Any:
    api_dependencies = api_dependencies_module()
    gateway = gateway_module()
    persistence = persistence_module()
    services = services_module()
    runtime_pkg = runtime_package()
    localdev = localdev_module()

    settings = local_settings(tmp_path)
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
        execution_template=execution_template(),
        health_reporter=api_dependencies._DefaultHealthReporter(settings),
        readiness_reporter=api_dependencies._DefaultReadinessReporter(settings),
    )


@dataclass(slots=True)
class DeferredRuntimeAdapter:
    runtime_name: str = "deferred-runtime"
    _sessions: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def capabilities(self) -> Any:
        return runtimes_module().RuntimeCapabilities()

    def prepare(self, request: Any) -> Any:
        runtimes = runtimes_module()
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
        return runtimes_module().RuntimeInvocationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            metadata=request.metadata,
        )

    def collect_result(self, session: Any, request: Any | None = None) -> Any:
        stored = self._sessions[session.session_id]["result"]
        return runtimes_module().RuntimeCollectionResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            ready=stored is not None,
            result=stored,
            metadata=() if request is None else request.metadata,
        )

    def request_cancellation(self, session: Any, request: Any) -> Any:
        domain = domain_module()
        runtimes = runtimes_module()
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
        runtimes = runtimes_module()
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
        executors = executors_module()
        return executors.SandboxCapabilities(
            supported_isolation_modes=(executors.SandboxIsolationMode.CONTAINER,),
            tenant_boundary_kind="namespace",
            supports_status_inspection=True,
            supports_cancellation=True,
            supports_cleanup=True,
            supports_separate_launch_phase=True,
        )

    def create(self, request: Any) -> Any:
        executors = executors_module()
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
            "inspect_calls": 0,
        }
        return sandbox

    def launch(self, sandbox: Any, request: Any | None = None) -> Any:
        executors = executors_module()
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
        domain = domain_module()
        executors = executors_module()
        state = self._sandboxes[sandbox.identity.resource_name]
        _ = _next_inspect_call(state)
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
        executors = executors_module()
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
        executors = executors_module()
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


@dataclass(slots=True)
class TimeoutSandboxExecutor(DeferredSandboxExecutor):
    executor_name: str = "timeout-executor"

    def inspect(self, sandbox: Any) -> Any:
        domain = domain_module()
        executors = executors_module()
        state = self._sandboxes[sandbox.identity.resource_name]
        if _next_inspect_call(state) == 1:
            return executors.SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=executors.SandboxStatus.RUNNING,
                observed_at=state["started_at"],
                started_at=state["started_at"],
            )

        finished_at = datetime(2026, 4, 16, 12, 20, tzinfo=UTC)
        state["status"] = executors.SandboxStatus.TIMED_OUT
        state["finished_at"] = finished_at
        return executors.SandboxInspection(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            status=executors.SandboxStatus.TIMED_OUT,
            observed_at=finished_at,
            started_at=state["started_at"],
            finished_at=finished_at,
            error=domain.TimeoutError(
                "sandbox exceeded execution timeout"
            ).as_details(),
        )


def build_deferred_api_dependencies(tmp_path: Path) -> Any:
    api_dependencies = api_dependencies_module()
    persistence = persistence_module()
    services = services_module()

    settings = local_settings(tmp_path)
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
        execution_template=execution_template(),
        health_reporter=api_dependencies._DefaultHealthReporter(settings),
        readiness_reporter=api_dependencies._DefaultReadinessReporter(settings),
    )

"""Dependency wiring and profile-aware default composition for the FastAPI app."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from os import path as os_path
from pathlib import Path
from typing import Any, Protocol, cast

from .auth import AuthSettingsLike, JWTPrincipalVerifier, PrincipalVerifier


class ExecutorSettingsLike(Protocol):
    backend: str
    isolation_mode: str


class RuntimeSettingsLike(Protocol):
    workspace_root: Path
    sandbox_image_reference: str | None


class PersistenceSettingsLike(Protocol):
    artifact_root: Path


class ObservabilitySettingsLike(Protocol):
    service_name: str


class KubernetesSettingsLike(Protocol):
    shared_state_server: str | None
    shared_state_path: str | None


class SettingsLike(Protocol):
    profile: object
    api: object
    auth: AuthSettingsLike
    executor: ExecutorSettingsLike
    gateway: object
    kubernetes: KubernetesSettingsLike
    persistence: PersistenceSettingsLike
    runtime: RuntimeSettingsLike
    observability: ObservabilitySettingsLike
    timeouts: object


class OrchestratorLike(Protocol):
    def submit(self, request: object) -> object: ...

    def poll(self, tenant_id: object, job_id: object) -> object: ...

    def get_status(self, tenant_id: object, job_id: object) -> object: ...

    def list_artifacts(self, tenant_id: object, job_id: object) -> object: ...

    def cancel(self, request: object) -> object: ...


class HealthReporter(Protocol):
    def build_report(self) -> object: ...


class ReadinessReporter(Protocol):
    def build_report(self) -> object: ...


def _config_module() -> Any:
    return import_module("agentsty_platform.config")


def _gateway_module() -> Any:
    return import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return import_module("agentsty_platform.observability")


def _persistence_module() -> Any:
    return import_module("agentsty_platform.persistence")


def _services_module() -> Any:
    return import_module("agentsty_platform.services")


def _runtimes_module() -> Any:
    return import_module("agentsty_platform.runtimes")


def _executor_package() -> Any:
    return import_module("agentsty_executor_kubernetes")


def _executors_module() -> Any:
    return import_module("agentsty_platform.executors")


def _localdev_module() -> Any:
    return import_module("agentsty_platform.localdev")


@dataclass(frozen=True, slots=True)
class ExecutionTemplate:
    """Internal execution defaults hidden behind the HTTP transport boundary."""

    sandbox_program: object
    sandbox_resources: object
    desired_isolation: object


@dataclass(frozen=True, slots=True)
class APIDependencies:
    """Small typed dependency bundle attached to the FastAPI app state."""

    settings: SettingsLike
    orchestrator: OrchestratorLike
    execution_template: ExecutionTemplate
    health_reporter: HealthReporter
    readiness_reporter: ReadinessReporter
    principal_verifier: PrincipalVerifier | None = None


@dataclass(frozen=True, slots=True)
class _DefaultHealthReporter:
    settings: SettingsLike
    orchestrator_ready: bool = True

    def build_report(self) -> object:
        observability = _observability_module()
        status = observability.HealthStatus.HEALTHY
        detail = (
            "service wiring complete"
            if self.orchestrator_ready
            else "service wiring missing"
        )
        if not self.orchestrator_ready:
            status = observability.HealthStatus.UNHEALTHY
        return observability.HealthReport.from_components(
            self.settings.observability.service_name,
            (
                observability.HealthComponent(
                    name="config", status=observability.HealthStatus.HEALTHY
                ),
                observability.HealthComponent(
                    name="orchestrator", status=status, detail=detail
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class _DefaultReadinessReporter:
    settings: SettingsLike
    orchestrator_ready: bool = True

    def build_report(self) -> object:
        observability = _observability_module()
        return observability.ReadinessReport.from_checks(
            self.settings.observability.service_name,
            (
                observability.ReadinessCheck(name="config-loaded", ready=True),
                observability.ReadinessCheck(
                    name="orchestrator-wired",
                    ready=self.orchestrator_ready,
                    detail=(
                        "shared execution orchestrator available"
                        if self.orchestrator_ready
                        else "shared execution orchestrator missing"
                    ),
                ),
            ),
        )


def create_default_dependencies(settings: object | None = None) -> APIDependencies:
    """Compose default wiring with an explicit local-development execution path."""

    config = _config_module()
    provided_settings = (
        settings if settings is not None else config.PlatformSettings.from_env()
    )
    effective_settings = cast(SettingsLike, provided_settings)

    gateway = _gateway_module()
    persistence = _persistence_module()
    services = _services_module()
    runtimes = _runtimes_module()
    executor_pkg = _executor_package()
    executors = _executors_module()
    localdev = _localdev_module()

    if _profile_name(effective_settings.profile) == "local":
        jobs = persistence.InMemoryJobRepository()
        artifact_metadata = persistence.InMemoryArtifactMetadataRepository()
        artifact_content = None
        gateway_client = gateway.InternalGatewayClient(
            settings=effective_settings,
            transport=gateway.LocalGatewayTransport(),
            token_provider=gateway.StaticInternalAuthTokenProvider(),
        )
        sandbox_executor = localdev.LocalProcessSandboxExecutor(
            executor_settings=effective_settings.executor,
            workspace_root=effective_settings.runtime.workspace_root,
        )
        template = ExecutionTemplate(
            sandbox_program=localdev.build_local_runner_program(
                environment=(
                    ("AGENTSTY_EXECUTION_MODE", "local_development"),
                    ("AGENTSTY_ISOLATION_GUARANTEE", "host_process_only"),
                )
            ),
            sandbox_resources=executors.SandboxResourceRequirements(
                cpu_millis=250,
                memory_mebibytes=512,
                ephemeral_storage_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.PROCESS,
        )
    else:
        non_local_persistence = persistence.build_non_local_persistence(
            effective_settings
        )
        jobs = non_local_persistence.jobs
        artifact_metadata = non_local_persistence.artifact_metadata
        artifact_content = non_local_persistence.artifact_content
        gateway_client = gateway.InternalGatewayClient(
            settings=effective_settings,
            transport=gateway.HTTPGatewayTransport(),
            token_provider=gateway.ServiceGatewayTokenProvider.from_settings(
                effective_settings
            ),
        )
        sandbox_executor = executor_pkg.KubernetesJobExecutor(
            control_plane=executor_pkg.ConfiguredKubernetesControlPlane.from_settings(
                effective_settings
            ),
            executor_settings=effective_settings.executor,
            shared_state_mount=_non_local_shared_state_mount(
                effective_settings,
                executor_pkg=executor_pkg,
            ),
        )
        image_reference = effective_settings.runtime.sandbox_image_reference
        if image_reference is None:
            raise ValueError(
                "non-local profiles must define runtime.sandbox_image_reference"
            )
        template = ExecutionTemplate(
            sandbox_program=localdev.build_packaged_runner_program(
                image_reference=image_reference,
            ),
            sandbox_resources=executors.SandboxResourceRequirements(
                cpu_millis=250,
                memory_mebibytes=512,
                ephemeral_storage_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.VIRTUAL_MACHINE,
        )
    runtime_adapter = runtimes.build_runtime_adapter(
        effective_settings,
        gateway_client,
    )
    orchestrator = services.ExecutionOrchestrator(
        settings=effective_settings,
        jobs=jobs,
        artifact_metadata=artifact_metadata,
        runtime_adapter=runtime_adapter,
        sandbox_executor=sandbox_executor,
        intake_service=services.RequestIntakeService(jobs=jobs),
        artifact_content=artifact_content,
    )
    return APIDependencies(
        settings=effective_settings,
        orchestrator=cast(OrchestratorLike, orchestrator),
        execution_template=template,
        health_reporter=_DefaultHealthReporter(effective_settings),
        readiness_reporter=_DefaultReadinessReporter(effective_settings),
        principal_verifier=(
            None
            if _profile_name(effective_settings.profile) == "local"
            else JWTPrincipalVerifier()
        ),
    )


def _profile_name(profile: object) -> str:
    value = getattr(profile, "value", profile)
    return cast(str, value)


def _non_local_shared_state_mount(
    settings: SettingsLike,
    *,
    executor_pkg: Any,
) -> object:
    runtime_root = Path(settings.runtime.workspace_root)
    artifact_root = Path(settings.persistence.artifact_root)
    mount_path = Path(os_path.commonpath((str(runtime_root), str(artifact_root))))
    if mount_path == Path(mount_path.anchor):
        raise ValueError(
            "non-local runtime workspace and artifact root must share a non-root mount path"
        )
    shared_state_server = settings.kubernetes.shared_state_server
    shared_state_path = settings.kubernetes.shared_state_path
    if shared_state_server is None or shared_state_path is None:
        raise ValueError("non-local shared state settings must be configured")
    return executor_pkg.KubernetesSharedStateMount(
        volume=executor_pkg.KubernetesJobVolume(
            name="agentsty-state",
            nfs=executor_pkg.KubernetesNFSVolumeSource(
                server=shared_state_server,
                path=shared_state_path,
            ),
        ),
        mounts=(
            executor_pkg.KubernetesVolumeMount(
                name="agentsty-state",
                mount_path=str(mount_path),
            ),
        ),
    )

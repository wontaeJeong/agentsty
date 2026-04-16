from __future__ import annotations

import importlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _api_dependencies_module() -> Any:
    return importlib.import_module("agentsty_api.dependencies")


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def _localdev_module() -> Any:
    return importlib.import_module("agentsty_platform.localdev")


def test_default_dependencies_use_explicit_local_executor_for_local_profile(
    tmp_path: Path,
) -> None:
    config = _config_module()
    dependencies_module = _api_dependencies_module()
    executors = _executors_module()

    settings = config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={"runtime": {"workspace_root": tmp_path / "runtime"}},
    )
    dependencies = dependencies_module.create_default_dependencies(settings)

    assert dependencies.settings.executor.backend == "local"
    assert dependencies.settings.executor.isolation_mode == "process"
    assert (
        dependencies.execution_template.desired_isolation
        is executors.SandboxIsolationMode.PROCESS
    )
    assert (
        "python"
        in Path(dependencies.execution_template.sandbox_program.command[-1]).name
    )
    assert dependencies.execution_template.sandbox_program.args == (
        "-m",
        "agentsty_platform.runner",
        "serve",
    )
    assert dependencies.orchestrator.sandbox_executor.executor_name == "local-process"


def test_default_dependencies_keep_kubernetes_executor_for_non_local_profile(
    tmp_path: Path,
) -> None:
    config = _config_module()
    dependencies_module = _api_dependencies_module()
    executors = _executors_module()
    gateway = importlib.import_module("agentsty_platform.gateway")
    persistence = importlib.import_module("agentsty_platform.persistence")
    runtime_pkg = importlib.import_module("agentsty_runtime_opencode")
    executor_pkg = importlib.import_module("agentsty_executor_kubernetes")

    settings = config.PlatformSettings.for_profile(
        config.EnvironmentProfile.DEV,
        overrides={
            "runtime": {"workspace_root": tmp_path / "shared" / "runtime"},
            "persistence": {
                "database_url": f"sqlite:///{tmp_path / 'shared' / 'runtime' / '_service_state' / 'nonlocal-persistence.sqlite3'}",
                "artifact_root": tmp_path / "shared" / "artifacts",
            },
        },
    )
    dependencies = dependencies_module.create_default_dependencies(settings)

    assert dependencies.settings.executor.backend == "kubernetes"
    assert dependencies.settings.persistence.database_url.startswith("sqlite:///")
    assert (
        dependencies.execution_template.desired_isolation
        is executors.SandboxIsolationMode.VIRTUAL_MACHINE
    )
    assert dependencies.orchestrator.sandbox_executor.executor_name == "kubernetes-job"
    assert isinstance(
        dependencies.orchestrator.jobs, persistence.PersistentJobRepository
    )
    assert isinstance(
        dependencies.orchestrator.artifact_metadata,
        persistence.PersistentArtifactMetadataRepository,
    )
    assert isinstance(
        dependencies.orchestrator.artifact_content,
        persistence.LocalFileArtifactContentStore,
    )
    assert isinstance(
        dependencies.orchestrator.runtime_adapter, runtime_pkg.OpenCodeRuntimeAdapter
    )
    assert isinstance(
        dependencies.orchestrator.runtime_adapter.gateway_client.transport,
        gateway.HTTPGatewayTransport,
    )
    assert isinstance(
        dependencies.orchestrator.runtime_adapter.gateway_client.token_provider,
        gateway.ServiceGatewayTokenProvider,
    )
    assert isinstance(
        dependencies.orchestrator.sandbox_executor.control_plane,
        executor_pkg.ConfiguredKubernetesControlPlane,
    )
    assert isinstance(
        dependencies.orchestrator.sandbox_executor.control_plane.api_client,
        executor_pkg.KubernetesApiClient,
    )
    assert (
        dependencies.execution_template.sandbox_program.image_reference
        == "ghcr.io/agentsty/agentsty-sandbox:dev"
    )
    assert not isinstance(
        dependencies.orchestrator.jobs,
        persistence.InMemoryJobRepository,
    )
    assert not isinstance(
        dependencies.orchestrator.artifact_metadata,
        persistence.InMemoryArtifactMetadataRepository,
    )
    assert not isinstance(
        dependencies.orchestrator.runtime_adapter.gateway_client.transport,
        gateway.LocalGatewayTransport,
    )
    assert not isinstance(
        dependencies.orchestrator.sandbox_executor.control_plane,
        executor_pkg.InMemoryKubernetesControlPlane,
    )


def test_default_dependencies_allow_non_local_app_boot_without_local_path_overrides() -> (
    None
):
    config = _config_module()
    dependencies_module = _api_dependencies_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.DEV)
    dependencies = dependencies_module.create_default_dependencies(settings)
    executor_pkg = importlib.import_module("agentsty_executor_kubernetes")

    assert dependencies.settings.profile == config.EnvironmentProfile.DEV
    assert dependencies.principal_verifier is not None
    assert isinstance(
        dependencies.orchestrator.sandbox_executor.shared_state_mount,
        executor_pkg.KubernetesSharedStateMount,
    )
    assert (
        dependencies.orchestrator.sandbox_executor.shared_state_mount.mounts[
            0
        ].mount_path
        == "/var/lib/agentsty/dev"
    )


def test_local_process_executor_launches_real_runner_and_cleans_up(
    tmp_path: Path,
) -> None:
    config = _config_module()
    domain = _domain_module()
    executors = _executors_module()
    localdev = _localdev_module()

    settings = config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={"runtime": {"workspace_root": tmp_path / "runtime"}},
    )
    executor = localdev.LocalProcessSandboxExecutor(
        executor_settings=settings.executor,
        workspace_root=settings.runtime.workspace_root,
    )
    tenant = domain.TenantId("tenant-local")
    request_id = domain.RequestId(tenant_id=tenant, value="req-local-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-local-1")
    sandbox = executor.create(
        executors.SandboxCreateRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            program=localdev.build_local_runner_program(),
            resources=executors.SandboxResourceRequirements(
                cpu_millis=100,
                memory_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.PROCESS,
        )
    )

    launch = executor.launch(
        sandbox,
        executors.SandboxLaunchRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            identity=sandbox.identity,
            requested_at=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
        ),
    )
    inspection = executor.inspect(sandbox)
    cleanup = executor.cleanup(sandbox)

    assert launch.identity.resource_kind == "process"
    assert inspection.status is executors.SandboxStatus.RUNNING
    assert cleanup.cleaned is True
    assert cleanup.released_resources[0].endswith("tenant-local/job-local-1")
    assert not (
        settings.runtime.workspace_root / "sandboxes" / tenant.value / job_id.value
    ).exists()


def test_local_process_executor_does_not_inherit_host_secrets(tmp_path: Path) -> None:
    config = _config_module()
    domain = _domain_module()
    executors = _executors_module()
    localdev = _localdev_module()

    settings = config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={"runtime": {"workspace_root": tmp_path / "runtime"}},
    )
    executor = localdev.LocalProcessSandboxExecutor(
        executor_settings=settings.executor,
        workspace_root=settings.runtime.workspace_root,
    )
    tenant = domain.TenantId("tenant-secret")
    request_id = domain.RequestId(tenant_id=tenant, value="req-secret-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-secret-1")
    sandbox = executor.create(
        executors.SandboxCreateRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            program=executors.SandboxProgramSpec(
                command=(sys.executable,),
                args=(
                    "-c",
                    "from pathlib import Path; import os; Path('env-check.txt').write_text(os.getenv('AWS_SECRET_ACCESS_KEY', 'missing'))",
                ),
            ),
            resources=executors.SandboxResourceRequirements(
                cpu_millis=100,
                memory_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.PROCESS,
        )
    )

    original = os.environ.get("AWS_SECRET_ACCESS_KEY")
    os.environ["AWS_SECRET_ACCESS_KEY"] = "top-secret"
    try:
        _ = executor.launch(sandbox)
        stored = executor._require_stored_sandbox(sandbox)
        assert stored.process is not None
        output_path = stored.working_directory / "env-check.txt"
        _ = stored.process.wait(timeout=5.0)
        inspection = executor.inspect(sandbox)
        inherited_secret = output_path.read_text(encoding="utf-8")
    finally:
        if original is None:
            del os.environ["AWS_SECRET_ACCESS_KEY"]
        else:
            os.environ["AWS_SECRET_ACCESS_KEY"] = original
        _ = executor.cleanup(sandbox)

    assert inspection.status is executors.SandboxStatus.SUCCEEDED
    assert inherited_secret == "missing"


def test_local_process_executor_scopes_storage_by_tenant(tmp_path: Path) -> None:
    config = _config_module()
    domain = _domain_module()
    executors = _executors_module()
    localdev = _localdev_module()

    settings = config.PlatformSettings.for_profile(
        config.EnvironmentProfile.LOCAL,
        overrides={"runtime": {"workspace_root": tmp_path / "runtime"}},
    )
    executor = localdev.LocalProcessSandboxExecutor(
        executor_settings=settings.executor,
        workspace_root=settings.runtime.workspace_root,
    )
    tenant_a = domain.TenantId("tenant-a")
    tenant_b = domain.TenantId("tenant-b")
    request_a = domain.RequestId(tenant_id=tenant_a, value="req-1")
    request_b = domain.RequestId(tenant_id=tenant_b, value="req-1")
    job_a = domain.JobId(tenant_id=tenant_a, value="shared-job")
    job_b = domain.JobId(tenant_id=tenant_b, value="shared-job")

    sandbox_a = executor.create(
        executors.SandboxCreateRequest(
            tenant_id=tenant_a,
            request_id=request_a,
            job_id=job_a,
            program=localdev.build_local_runner_program(),
            resources=executors.SandboxResourceRequirements(
                cpu_millis=100,
                memory_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.PROCESS,
        )
    )
    sandbox_b = executor.create(
        executors.SandboxCreateRequest(
            tenant_id=tenant_b,
            request_id=request_b,
            job_id=job_b,
            program=localdev.build_local_runner_program(),
            resources=executors.SandboxResourceRequirements(
                cpu_millis=100,
                memory_mebibytes=128,
            ),
            desired_isolation=executors.SandboxIsolationMode.PROCESS,
        )
    )

    assert sandbox_a.identity.resource_name != sandbox_b.identity.resource_name
    assert executor.inspect(sandbox_a).status is executors.SandboxStatus.CREATED
    assert executor.inspect(sandbox_b).status is executors.SandboxStatus.CREATED

    _ = executor.cleanup(sandbox_a)
    _ = executor.cleanup(sandbox_b)

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


def _executors_module() -> Any:
    return importlib.import_module("agentsty_platform.executors")


def _kubernetes_module() -> Any:
    return importlib.import_module("agentsty_executor_kubernetes")


def _create_request(
    tenant: Any,
    request_id: Any,
    job_id: Any,
    *,
    timeouts: Any | None = None,
) -> Any:
    domain = _domain_module()
    executors = _executors_module()
    return executors.SandboxCreateRequest(
        tenant_id=tenant,
        request_id=request_id,
        job_id=job_id,
        program=executors.SandboxProgramSpec(
            command=("python",),
            args=("-m", "agentsty_runtime_opencode"),
            environment=(("AGENTSTY_MODE", "test"),),
            working_directory="/workspace",
            image_reference="ghcr.io/agentsty/agentsty-sandbox:test",
        ),
        resources=executors.SandboxResourceRequirements(
            cpu_millis=250,
            memory_mebibytes=512,
            ephemeral_storage_mebibytes=256,
        ),
        timeouts=(timeouts if timeouts is not None else domain.ExecutionTimeouts()),
        desired_isolation=executors.SandboxIsolationMode.VIRTUAL_MACHINE,
        metadata=(("trace_id", "trace-1"),),
    )


@dataclass(slots=True)
class _FakeKubernetesApiClient:
    server_url: str = "https://kubernetes.default.svc.cluster.local"
    boundaries: list[Any] = field(default_factory=list)
    jobs: dict[tuple[str, str], Any] = field(default_factory=dict)

    def ensure_namespace(self, boundary: Any) -> None:
        self.boundaries.append(boundary)

    def create_job(self, manifest: Any) -> None:
        key = (manifest.tenant_boundary.namespace, manifest.job_name)
        if key in self.jobs:
            raise ValueError("job already exists")
        self.jobs[key] = _kubernetes_module().KubernetesJobObservation(
            manifest=manifest,
            phase=_kubernetes_module().KubernetesJobPhase.PENDING,
        )

    def read_job(self, namespace: str, job_name: str) -> Any | None:
        return self.jobs.get((namespace, job_name))

    def cancel_job(
        self,
        namespace: str,
        job_name: str,
        *,
        requested_at: datetime,
        reason: str | None = None,
        error: object | None = None,
    ) -> bool:
        key = (namespace, job_name)
        observation = self.jobs.get(key)
        if observation is None or observation.phase.is_terminal:
            return False
        self.jobs[key] = observation.with_phase(
            _kubernetes_module().KubernetesJobPhase.CANCELLED,
            observed_at=requested_at,
            started_at=observation.started_at,
            finished_at=requested_at,
            cancellation_requested_at=requested_at,
            exit_code=143,
            message=reason,
            error=error,
        )
        return True

    def delete_job(self, namespace: str, job_name: str) -> bool:
        return self.jobs.pop((namespace, job_name), None) is not None


class _Api404(Exception):
    def __init__(self) -> None:
        super().__init__("not found")
        self.status = 404


@dataclass(slots=True)
class _FakeCoreApi:
    namespaces: dict[str, object] = field(default_factory=dict)
    service_accounts: dict[tuple[str, str], object] = field(default_factory=dict)
    resource_quotas: dict[tuple[str, str], object] = field(default_factory=dict)
    limit_ranges: dict[tuple[str, str], object] = field(default_factory=dict)

    def read_namespace(self, name: str) -> object:
        if name not in self.namespaces:
            raise _Api404()
        return self.namespaces[name]

    def create_namespace(self, body: Any) -> object:
        metadata = body["metadata"]
        self.namespaces[metadata["name"]] = body
        return body

    def read_namespaced_service_account(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.service_accounts:
            raise _Api404()
        return self.service_accounts[key]

    def create_namespaced_service_account(self, namespace: str, body: Any) -> object:
        self.service_accounts[(namespace, body["metadata"]["name"])] = body
        return body

    def read_namespaced_resource_quota(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.resource_quotas:
            raise _Api404()
        return self.resource_quotas[key]

    def create_namespaced_resource_quota(self, namespace: str, body: Any) -> object:
        self.resource_quotas[(namespace, body["metadata"]["name"])] = body
        return body

    def read_namespaced_limit_range(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.limit_ranges:
            raise _Api404()
        return self.limit_ranges[key]

    def create_namespaced_limit_range(self, namespace: str, body: Any) -> object:
        self.limit_ranges[(namespace, body["metadata"]["name"])] = body
        return body

    def delete_collection_namespaced_pod(
        self,
        namespace: str,
        *,
        label_selector: str,
        body: object,
    ) -> object:
        return {"namespace": namespace, "label_selector": label_selector, "body": body}


@dataclass(slots=True)
class _FakeRbacApi:
    roles: dict[tuple[str, str], object] = field(default_factory=dict)
    role_bindings: dict[tuple[str, str], object] = field(default_factory=dict)

    def read_namespaced_role(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.roles:
            raise _Api404()
        return self.roles[key]

    def create_namespaced_role(self, namespace: str, body: Any) -> object:
        self.roles[(namespace, body["metadata"]["name"])] = body
        return body

    def read_namespaced_role_binding(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.role_bindings:
            raise _Api404()
        return self.role_bindings[key]

    def create_namespaced_role_binding(self, namespace: str, body: Any) -> object:
        self.role_bindings[(namespace, body["metadata"]["name"])] = body
        return body


@dataclass(slots=True)
class _FakeNetworkingApi:
    network_policies: dict[tuple[str, str], object] = field(default_factory=dict)

    def read_namespaced_network_policy(self, name: str, namespace: str) -> object:
        key = (namespace, name)
        if key not in self.network_policies:
            raise _Api404()
        return self.network_policies[key]

    def create_namespaced_network_policy(self, namespace: str, body: Any) -> object:
        self.network_policies[(namespace, body["metadata"]["name"])] = body
        return body


def test_kubernetes_executor_models_namespace_isolation_and_job_lifecycle() -> None:
    config = _config_module()
    domain = _domain_module()
    executors = _executors_module()
    kubernetes = _kubernetes_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.PRODUCTION)
    control_plane = kubernetes.InMemoryKubernetesControlPlane()
    executor = kubernetes.KubernetesJobExecutor(
        control_plane=control_plane,
        executor_settings=settings.executor,
        isolation=kubernetes.KubernetesJobIsolationSettings(
            runtime_class_name="kata-clh"
        ),
        shared_state_mount=kubernetes.KubernetesSharedStateMount(
            volume=kubernetes.KubernetesJobVolume(
                name="agentsty-state",
                nfs=kubernetes.KubernetesNFSVolumeSource(
                    server="agentsty-state.production.internal",
                    path="/exports/agentsty/production",
                ),
            ),
            mounts=(
                kubernetes.KubernetesVolumeMount(
                    name="agentsty-state",
                    mount_path="/var/lib/agentsty/production",
                ),
            ),
        ),
        job_resources=kubernetes.KubernetesJobResources(
            cpu_request_millis=250,
            cpu_limit_millis=500,
            memory_request_mebibytes=512,
            memory_limit_mebibytes=1024,
            ephemeral_storage_limit_mebibytes=512,
        ),
    )

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-1")
    job_id = domain.JobId(tenant_id=tenant, value="job-1")
    sandbox = executor.create(
        _create_request(tenant, request_id, job_id, timeouts=settings.timeouts)
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

    manifest = control_plane.read_job(
        sandbox.identity.boundary.boundary_name,
        sandbox.identity.resource_name,
    )
    assert manifest is not None
    control_plane.mark_running(
        sandbox.identity.boundary.boundary_name,
        sandbox.identity.resource_name,
        started_at=datetime(2026, 4, 16, 12, 0, 2, tzinfo=UTC),
    )
    control_plane.mark_succeeded(
        sandbox.identity.boundary.boundary_name,
        sandbox.identity.resource_name,
        finished_at=datetime(2026, 4, 16, 12, 0, 5, tzinfo=UTC),
    )
    inspection = executor.inspect(sandbox)
    cleanup = executor.cleanup(sandbox)

    assert executor.executor_name == kubernetes.KUBERNETES_EXECUTOR_NAME
    assert executor.capabilities.tenant_boundary_kind == "namespace"
    assert sandbox.identity.provider == "kubernetes"
    assert sandbox.identity.boundary.boundary_name.startswith("agentsty-")
    assert control_plane.resource_quotas[sandbox.identity.boundary.boundary_name] == (
        "tenant-sandbox-quota"
    )
    assert control_plane.limit_ranges[sandbox.identity.boundary.boundary_name] == (
        "tenant-sandbox-limits"
    )
    assert control_plane.roles[sandbox.identity.boundary.boundary_name] == (
        "agentsty-sandbox-runner"
    )
    assert control_plane.role_bindings[sandbox.identity.boundary.boundary_name] == (
        "agentsty-sandbox-runner"
    )
    assert control_plane.network_policies[sandbox.identity.boundary.boundary_name] == (
        "tenant-sandbox-default-deny"
    )
    assert launch.deadline_at is not None
    assert manifest.manifest.tenant_boundary.service_account_name.startswith("sa-")
    assert manifest.manifest.isolation.runtime_class_name == "kata-clh"
    assert manifest.manifest.isolation.require_kata_runtime is True
    assert manifest.manifest.resources.cpu_limit_millis == 500
    assert manifest.manifest.volume_mounts == (
        kubernetes.KubernetesVolumeMount(
            name="agentsty-state",
            mount_path="/var/lib/agentsty/production",
        ),
    )
    assert manifest.manifest.volumes == (
        kubernetes.KubernetesJobVolume(
            name="agentsty-state",
            nfs=kubernetes.KubernetesNFSVolumeSource(
                server="agentsty-state.production.internal",
                path="/exports/agentsty/production",
            ),
        ),
    )
    assert manifest.manifest.active_deadline_seconds == 1200
    assert manifest.manifest.ttl_seconds_after_finished == 300
    assert inspection.status is executors.SandboxStatus.SUCCEEDED
    assert inspection.exit_code == 0
    assert cleanup.cleaned is True


def test_kubernetes_executor_supports_prelaunch_cancellation_and_timeout_mapping() -> (
    None
):
    config = _config_module()
    domain = _domain_module()
    executors = _executors_module()
    kubernetes = _kubernetes_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.PRODUCTION)
    control_plane = kubernetes.InMemoryKubernetesControlPlane()
    executor = kubernetes.KubernetesJobExecutor(
        control_plane=control_plane,
        executor_settings=settings.executor,
    )

    tenant = domain.TenantId("tenant-a")
    request_id = domain.RequestId(tenant_id=tenant, value="req-2")
    job_id = domain.JobId(tenant_id=tenant, value="job-2")
    sandbox = executor.create(
        _create_request(tenant, request_id, job_id, timeouts=settings.timeouts)
    )
    cancellation = executor.request_cancellation(
        sandbox,
        executors.SandboxCancellationRequest(
            tenant_id=tenant,
            request_id=request_id,
            job_id=job_id,
            identity=sandbox.identity,
            reason="operator requested stop",
            requested_at=datetime(2026, 4, 16, 12, 1, tzinfo=UTC),
        ),
    )
    inspection = executor.inspect(sandbox)
    cleanup = executor.cleanup(sandbox)

    tenant_two = domain.TenantId("tenant-b")
    request_two = domain.RequestId(tenant_id=tenant_two, value="req-3")
    job_two = domain.JobId(tenant_id=tenant_two, value="job-3")
    timeout_sandbox = executor.create(
        _create_request(tenant_two, request_two, job_two, timeouts=settings.timeouts)
    )
    _ = executor.launch(timeout_sandbox)
    control_plane.mark_running(
        timeout_sandbox.identity.boundary.boundary_name,
        timeout_sandbox.identity.resource_name,
        started_at=datetime(2026, 4, 16, 12, 2, tzinfo=UTC),
    )
    control_plane.mark_timed_out(
        timeout_sandbox.identity.boundary.boundary_name,
        timeout_sandbox.identity.resource_name,
        message="job exceeded active deadline",
        finished_at=datetime(2026, 4, 16, 12, 22, tzinfo=UTC),
    )
    timeout_inspection = executor.inspect(timeout_sandbox)

    assert cancellation.acknowledged is True
    assert inspection.status is executors.SandboxStatus.CANCELLED
    assert inspection.error.category is domain.ErrorCategory.CANCELLATION
    assert cleanup.cleaned is True
    assert timeout_inspection.status is executors.SandboxStatus.TIMED_OUT
    assert timeout_inspection.error.category is domain.ErrorCategory.TIMEOUT
    assert timeout_inspection.identity.boundary.boundary_name != (
        sandbox.identity.boundary.boundary_name
    )


def test_kubernetes_api_client_provisions_namespace_isolation_controls() -> None:
    kubernetes = _kubernetes_module()

    client = kubernetes.KubernetesApiClient(
        server_url="https://kubernetes.default.svc.cluster.local",
        profile="production",
    )
    core_api = _FakeCoreApi()
    rbac_api = _FakeRbacApi()
    networking_api = _FakeNetworkingApi()
    client._core_api = core_api
    client._batch_api = cast(Any, object())
    client._rbac_api = rbac_api
    client._networking_api = networking_api
    boundary = kubernetes.KubernetesTenantBoundary(
        namespace="agentsty-tenant-sample-prod",
        service_account_name="sa-tenant-sample-prod",
        labels=(("app.kubernetes.io/part-of", "agentsty"),),
        annotations=(("agentsty.io/tenant", "tenant-sample-prod"),),
    )

    client.ensure_namespace(boundary)

    quota = cast(
        Any,
        core_api.resource_quotas[(boundary.namespace, "tenant-sandbox-quota")],
    )
    limit_range = cast(
        Any,
        core_api.limit_ranges[(boundary.namespace, "tenant-sandbox-limits")],
    )
    role = cast(Any, rbac_api.roles[(boundary.namespace, "agentsty-sandbox-runner")])
    role_binding = cast(
        Any,
        rbac_api.role_bindings[(boundary.namespace, "agentsty-sandbox-runner")],
    )
    network_policy = cast(
        Any,
        networking_api.network_policies[
            (boundary.namespace, "tenant-sandbox-default-deny")
        ],
    )

    assert quota["spec"]["hard"]["count/jobs.batch"] == "12"
    assert quota["spec"]["hard"]["limits.memory"] == "16Gi"
    assert limit_range["spec"]["limits"][0]["defaultRequest"] == {
        "cpu": "500m",
        "memory": "1Gi",
    }
    assert limit_range["spec"]["limits"][0]["default"] == {
        "cpu": "2",
        "memory": "2Gi",
    }
    assert role["rules"][0]["resources"] == ["pods", "pods/log"]
    assert role_binding["subjects"][0]["name"] == boundary.service_account_name
    assert network_policy["spec"]["ingress"] == []
    assert len(network_policy["spec"]["egress"]) == 4


def test_kubernetes_api_client_job_body_mounts_shared_state_volume() -> None:
    kubernetes = _kubernetes_module()

    client = kubernetes.KubernetesApiClient(
        server_url="https://kubernetes.default.svc.cluster.local",
        profile="production",
    )
    boundary = kubernetes.KubernetesTenantBoundary(
        namespace="agentsty-production-tenant-a",
        service_account_name="agentsty-production-runner",
    )
    manifest = kubernetes.KubernetesJobManifest(
        identity=object(),
        tenant_boundary=boundary,
        job_name="sandbox-job-1",
        image_reference="ghcr.io/agentsty/agentsty-sandbox:prod",
        command=("python",),
        volume_mounts=(
            kubernetes.KubernetesVolumeMount(
                name="agentsty-state",
                mount_path="/var/lib/agentsty/production",
            ),
        ),
        volumes=(
            kubernetes.KubernetesJobVolume(
                name="agentsty-state",
                nfs=kubernetes.KubernetesNFSVolumeSource(
                    server="agentsty-state.production.internal",
                    path="/exports/agentsty/production",
                ),
            ),
        ),
    )

    body = client._job_body(manifest)
    pod_spec = body["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert container["volumeMounts"] == [
        {
            "name": "agentsty-state",
            "mountPath": "/var/lib/agentsty/production",
            "readOnly": False,
        }
    ]
    assert pod_spec["volumes"] == [
        {
            "name": "agentsty-state",
            "nfs": {
                "server": "agentsty-state.production.internal",
                "path": "/exports/agentsty/production",
                "readOnly": False,
            },
        }
    ]


def test_configured_kubernetes_control_plane_uses_client_backed_non_local_path() -> (
    None
):
    config = _config_module()
    kubernetes = _kubernetes_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.PRODUCTION)
    fake_client = _FakeKubernetesApiClient()
    control_plane = kubernetes.ConfiguredKubernetesControlPlane.from_settings(
        settings,
        api_client=fake_client,
    )
    boundary = kubernetes.KubernetesTenantBoundary(
        namespace="agentsty-production-tenant-a",
        service_account_name="agentsty-production-runner",
        labels=(("app.kubernetes.io/part-of", "agentsty"),),
        annotations=(("agentsty.io/tenant", "tenant-a"),),
    )
    manifest = kubernetes.KubernetesJobManifest(
        identity=object(),
        tenant_boundary=boundary,
        job_name="sandbox-job-1",
        image_reference="ghcr.io/agentsty/agentsty-sandbox:prod",
        command=("python",),
    )

    control_plane.ensure_namespace(boundary)
    control_plane.create_job(manifest)
    observation = control_plane.read_job(boundary.namespace, manifest.job_name)
    cancelled = control_plane.cancel_job(
        boundary.namespace,
        manifest.job_name,
        requested_at=datetime(2026, 4, 16, 12, 5, tzinfo=UTC),
        reason="operator stop",
    )
    deleted = control_plane.delete_job(boundary.namespace, manifest.job_name)

    assert control_plane.api_server_url == fake_client.server_url
    assert control_plane.namespace_prefix == "agentsty-production"
    assert control_plane.service_account_prefix == "agentsty-production-runner"
    assert fake_client.boundaries == [boundary]
    assert observation is not None
    assert cancelled is True
    assert deleted is True

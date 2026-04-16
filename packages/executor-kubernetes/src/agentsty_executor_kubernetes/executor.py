"""Kubernetes Job executor implementation using a local control-plane seam."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import import_module
from typing import Protocol, cast

from .control_plane import KubernetesControlPlane
from .models import (
    KubernetesJobExecutorSettings,
    KubernetesJobIsolationSettings,
    KubernetesJobManifest,
    KubernetesJobObservation,
    KubernetesJobPhase,
    KubernetesJobResources,
    KubernetesSharedStateMount,
    KubernetesTenantBoundary,
    SandboxResourceIdentityLike,
)

KUBERNETES_EXECUTOR_NAME = "kubernetes-job"

_DNS_SAFE_PATTERN = re.compile(r"[^a-z0-9-]+")


class ExecutorSettingsLike(Protocol):
    backend: str
    isolation_mode: str
    allow_privileged_containers: bool


class ExecutionTimeoutsLike(Protocol):
    execution_timeout_seconds: int


class SandboxProgramLike(Protocol):
    command: tuple[str, ...]
    args: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    working_directory: str | None
    image_reference: str | None


class SandboxCreateRequestLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    program: SandboxProgramLike
    resources: object
    timeouts: ExecutionTimeoutsLike
    desired_isolation: object
    metadata: tuple[tuple[str, str], ...]


class SandboxIdentityLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    resource_name: str
    boundary: BoundaryLike


class SandboxHandleLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    identity: SandboxIdentityLike
    created_at: datetime
    timeouts: ExecutionTimeoutsLike


class SandboxLaunchRequestLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    identity: SandboxIdentityLike
    requested_at: datetime
    metadata: tuple[tuple[str, str], ...]


class SandboxCancellationRequestLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    identity: SandboxIdentityLike
    reason: str | None
    requested_at: datetime
    metadata: tuple[tuple[str, str], ...]


class SandboxCleanupRequestLike(Protocol):
    tenant_id: TenantLike
    request_id: ScopedIdLike
    job_id: ScopedIdLike
    identity: SandboxIdentityLike
    requested_at: datetime
    metadata: tuple[tuple[str, str], ...]


class BoundaryLike(Protocol):
    boundary_name: str


class TenantLike(Protocol):
    value: str


class ScopedIdLike(Protocol):
    value: str


class ErrorDetailsLike(Protocol):
    category: object
    message: str


class DomainErrorLike(Protocol):
    def as_details(self) -> ErrorDetailsLike: ...


class DomainErrorFactory(Protocol):
    def __call__(self, message: str) -> DomainErrorLike: ...


class DomainModuleLike(Protocol):
    SandboxCreationError: DomainErrorFactory
    InternalError: DomainErrorFactory
    RuntimeExecutionError: DomainErrorFactory
    TimeoutError: DomainErrorFactory
    CancellationError: DomainErrorFactory


class SandboxIsolationModeNamespace(Protocol):
    PROCESS: object
    CONTAINER: object
    VIRTUAL_MACHINE: object


class SandboxStatusNamespace(Protocol):
    CREATED: object
    PENDING: object
    RUNNING: object
    SUCCEEDED: object
    FAILED: object
    TIMED_OUT: object
    CANCELLED: object
    UNKNOWN: object


class SandboxCapabilitiesFactory(Protocol):
    def __call__(
        self,
        *,
        supported_isolation_modes: tuple[object, ...],
        tenant_boundary_kind: str,
        supports_status_inspection: bool,
        supports_cancellation: bool,
        supports_cleanup: bool,
        supports_separate_launch_phase: bool,
    ) -> object: ...


class TenantResourceBoundaryFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        boundary_kind: str,
        boundary_name: str,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxResourceIdentityFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        executor_name: str,
        provider: str,
        resource_kind: str,
        resource_name: str,
        boundary: object,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxHandleFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        executor_name: str,
        identity: object,
        program: SandboxProgramLike,
        resources: object,
        timeouts: ExecutionTimeoutsLike,
        desired_isolation: object,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxLaunchReceiptFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        identity: SandboxIdentityLike,
        accepted_at: datetime,
        deadline_at: datetime,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxInspectionFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        identity: SandboxIdentityLike,
        status: object,
        observed_at: datetime,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        cancellation_requested_at: datetime | None = None,
        deadline_at: datetime | None = None,
        exit_code: int | None = None,
        error: ErrorDetailsLike | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxCancellationReceiptFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        identity: SandboxIdentityLike,
        acknowledged: bool,
        requested_at: datetime,
        error: ErrorDetailsLike | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class SandboxCleanupResultFactory(Protocol):
    def __call__(
        self,
        *,
        tenant_id: TenantLike,
        request_id: ScopedIdLike,
        job_id: ScopedIdLike,
        identity: SandboxIdentityLike,
        cleaned: bool,
        cleaned_at: datetime,
        released_resources: tuple[str, ...] = (),
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class ExecutorsModuleLike(Protocol):
    SandboxCapabilities: SandboxCapabilitiesFactory
    SandboxIsolationMode: SandboxIsolationModeNamespace
    SandboxStatus: SandboxStatusNamespace
    TenantResourceBoundary: TenantResourceBoundaryFactory
    SandboxResourceIdentity: SandboxResourceIdentityFactory
    SandboxHandle: SandboxHandleFactory
    SandboxLaunchReceipt: SandboxLaunchReceiptFactory
    SandboxInspection: SandboxInspectionFactory
    SandboxCancellationReceipt: SandboxCancellationReceiptFactory
    SandboxCleanupResult: SandboxCleanupResultFactory

    def status_for_error(self, error: ErrorDetailsLike) -> object: ...


def _domain_module() -> DomainModuleLike:
    return cast(
        DomainModuleLike,
        cast(object, import_module("agentsty_platform.domain")),
    )


def _executors_module() -> ExecutorsModuleLike:
    return cast(
        ExecutorsModuleLike,
        cast(object, import_module("agentsty_platform.executors")),
    )


def _safe_name(prefix: str, raw_value: str, *, max_length: int = 63) -> str:
    value = _DNS_SAFE_PATTERN.sub("-", raw_value.lower()).strip("-")
    if not value:
        value = "sandbox"
    if prefix:
        value = f"{prefix}{value}"
    if len(value) <= max_length:
        return value
    suffix = hex(abs(hash(raw_value)))[2:10]
    cutoff = max_length - len(suffix) - 1
    return f"{value[:cutoff].rstrip('-')}-{suffix}"


@dataclass(slots=True)
class _StoredSandbox:
    sandbox: SandboxHandleLike
    manifest: KubernetesJobManifest
    launched: bool = False
    prelaunch_inspection: object | None = None


@dataclass(slots=True)
class KubernetesJobExecutor:
    """Tenant-aware sandbox executor that renders and manages Kubernetes Jobs."""

    control_plane: KubernetesControlPlane
    executor_settings: ExecutorSettingsLike
    job_settings: KubernetesJobExecutorSettings = field(
        default_factory=KubernetesJobExecutorSettings
    )
    isolation: KubernetesJobIsolationSettings = field(
        default_factory=KubernetesJobIsolationSettings
    )
    job_resources: KubernetesJobResources = field(
        default_factory=lambda: KubernetesJobResources(
            cpu_request_millis=250,
            cpu_limit_millis=500,
            memory_request_mebibytes=512,
            memory_limit_mebibytes=512,
            ephemeral_storage_limit_mebibytes=512,
        )
    )
    shared_state_mount: KubernetesSharedStateMount | None = None
    _sandboxes: dict[str, _StoredSandbox] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.executor_settings.backend != "kubernetes":
            raise ValueError("executor settings backend must be 'kubernetes'")
        if self.executor_settings.allow_privileged_containers:
            raise ValueError("privileged containers must remain disabled")

    @property
    def executor_name(self) -> str:
        return KUBERNETES_EXECUTOR_NAME

    @property
    def capabilities(self) -> object:
        executors = _executors_module()
        return executors.SandboxCapabilities(
            supported_isolation_modes=(
                executors.SandboxIsolationMode.CONTAINER,
                executors.SandboxIsolationMode.VIRTUAL_MACHINE,
            ),
            tenant_boundary_kind="namespace",
            supports_status_inspection=True,
            supports_cancellation=True,
            supports_cleanup=True,
            supports_separate_launch_phase=True,
        )

    def create(self, request: SandboxCreateRequestLike) -> object:
        domain = _domain_module()
        executors = _executors_module()
        if request.program.image_reference is None:
            raise cast(
                Exception,
                cast(
                    object,
                    domain.SandboxCreationError(
                        "kubernetes sandbox execution requires an image reference"
                    ),
                ),
            )
        if request.desired_isolation == executors.SandboxIsolationMode.PROCESS:
            raise cast(
                Exception,
                cast(
                    object,
                    domain.SandboxCreationError(
                        "kubernetes executor does not support process isolation"
                    ),
                ),
            )
        if (
            request.desired_isolation == executors.SandboxIsolationMode.VIRTUAL_MACHINE
            and self.isolation.runtime_class_name is None
        ):
            raise cast(
                Exception,
                cast(
                    object,
                    domain.SandboxCreationError(
                        "virtual machine isolation requires a runtime class"
                    ),
                ),
            )

        tenant_value = request.tenant_id.value
        namespace = _safe_name(self.job_settings.namespace_prefix, tenant_value)
        job_name = _safe_name(self.job_settings.job_name_prefix, request.job_id.value)
        service_account_name = _safe_name("sa-", tenant_value)
        boundary = KubernetesTenantBoundary(
            namespace=namespace,
            service_account_name=service_account_name,
            labels=(("app.kubernetes.io/part-of", "agentsty"),),
            annotations=(
                ("agentsty.io/tenant", tenant_value),
                ("agentsty.io/request-id", request.request_id.value),
                ("agentsty.io/job-id", request.job_id.value),
            ),
        )
        self.control_plane.ensure_namespace(boundary)
        resource_boundary = executors.TenantResourceBoundary(
            tenant_id=request.tenant_id,
            boundary_kind="namespace",
            boundary_name=boundary.namespace,
            metadata=(("service_account", boundary.service_account_name),),
        )
        identity = executors.SandboxResourceIdentity(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            executor_name=self.executor_name,
            provider="kubernetes",
            resource_kind="job",
            resource_name=job_name,
            boundary=resource_boundary,
            metadata=(("service_account", boundary.service_account_name),),
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
            metadata=request.metadata + (("provider", "kubernetes"),),
        )
        manifest = KubernetesJobManifest(
            identity=cast(SandboxResourceIdentityLike, identity),
            tenant_boundary=boundary,
            job_name=job_name,
            image_reference=request.program.image_reference,
            command=request.program.command,
            args=request.program.args,
            environment=request.program.environment,
            volume_mounts=(
                ()
                if self.shared_state_mount is None
                else self.shared_state_mount.mounts
            ),
            volumes=(
                ()
                if self.shared_state_mount is None
                else (self.shared_state_mount.volume,)
            ),
            working_directory=request.program.working_directory,
            labels=(
                ("app.kubernetes.io/name", "agentsty-sandbox"),
                ("agentsty.io/tenant", tenant_value),
            ),
            annotations=request.metadata,
            active_deadline_seconds=request.timeouts.execution_timeout_seconds,
            ttl_seconds_after_finished=self.job_settings.ttl_seconds_after_finished,
            backoff_limit=self.job_settings.backoff_limit,
            image_pull_policy=self.job_settings.image_pull_policy,
            resources=self.job_resources,
            isolation=self.isolation,
        )
        self._sandboxes[job_name] = _StoredSandbox(
            sandbox=cast(SandboxHandleLike, sandbox),
            manifest=manifest,
        )
        return sandbox

    def launch(
        self,
        sandbox: SandboxHandleLike,
        request: SandboxLaunchRequestLike | None = None,
    ) -> object:
        executors = _executors_module()
        state = self._require_sandbox(sandbox)
        metadata: tuple[tuple[str, str], ...] = ()
        accepted_at = sandbox.created_at
        if request is not None:
            self._require_request_match(sandbox, request)
            metadata = request.metadata
            accepted_at = request.requested_at

        if not state.launched and state.prelaunch_inspection is None:
            self.control_plane.create_job(state.manifest)
            state.launched = True
        elif state.prelaunch_inspection is None and state.launched:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().SandboxCreationError(
                        "sandbox has already been launched"
                    ),
                ),
            )

        return executors.SandboxLaunchReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            accepted_at=accepted_at,
            deadline_at=accepted_at
            + timedelta(seconds=sandbox.timeouts.execution_timeout_seconds),
            metadata=metadata + (("provider", "kubernetes"),),
        )

    def inspect(self, sandbox: SandboxHandleLike) -> object:
        executors = _executors_module()
        state = self._require_sandbox(sandbox)
        if state.prelaunch_inspection is not None:
            return state.prelaunch_inspection
        if not state.launched:
            return executors.SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=executors.SandboxStatus.CREATED,
                observed_at=sandbox.created_at,
                deadline_at=sandbox.created_at
                + timedelta(seconds=sandbox.timeouts.execution_timeout_seconds),
                metadata=(("provider", "kubernetes"),),
            )
        observation = self.control_plane.read_job(
            state.manifest.tenant_boundary.namespace,
            state.manifest.job_name,
        )
        if observation is None:
            details = (
                _domain_module()
                .InternalError("kubernetes job is missing from the control plane")
                .as_details()
            )
            return executors.SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=executors.status_for_error(details),
                observed_at=sandbox.created_at,
                finished_at=sandbox.created_at,
                deadline_at=sandbox.created_at
                + timedelta(seconds=sandbox.timeouts.execution_timeout_seconds),
                error=details,
                metadata=(("provider", "kubernetes"),),
            )
        return self._inspection_from_observation(sandbox, observation)

    def request_cancellation(
        self,
        sandbox: SandboxHandleLike,
        request: SandboxCancellationRequestLike,
    ) -> object:
        domain = _domain_module()
        executors = _executors_module()
        state = self._require_sandbox(sandbox)
        self._require_request_match(sandbox, request)

        if state.prelaunch_inspection is not None:
            return executors.SandboxCancellationReceipt(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                acknowledged=False,
                requested_at=request.requested_at,
                error=domain.CancellationError(
                    "sandbox cancellation was already completed"
                ).as_details(),
                metadata=request.metadata + (("provider", "kubernetes"),),
            )

        if not state.launched:
            details = domain.CancellationError(
                request.reason or "sandbox launch was cancelled before submission"
            ).as_details()
            state.prelaunch_inspection = executors.SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=executors.SandboxStatus.CANCELLED,
                observed_at=request.requested_at,
                finished_at=request.requested_at,
                cancellation_requested_at=request.requested_at,
                deadline_at=request.requested_at
                + timedelta(seconds=sandbox.timeouts.execution_timeout_seconds),
                error=details,
                metadata=request.metadata + (("provider", "kubernetes"),),
            )
            return executors.SandboxCancellationReceipt(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                acknowledged=True,
                requested_at=request.requested_at,
                metadata=request.metadata + (("provider", "kubernetes"),),
            )

        acknowledged = self.control_plane.cancel_job(
            state.manifest.tenant_boundary.namespace,
            state.manifest.job_name,
            requested_at=request.requested_at,
            reason=request.reason,
            error=domain.CancellationError(
                request.reason or "sandbox execution cancelled"
            ).as_details(),
        )
        if acknowledged:
            return executors.SandboxCancellationReceipt(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                acknowledged=True,
                requested_at=request.requested_at,
                metadata=request.metadata + (("provider", "kubernetes"),),
            )
        return executors.SandboxCancellationReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            acknowledged=False,
            requested_at=request.requested_at,
            error=domain.CancellationError(
                "sandbox execution already reached a terminal state"
            ).as_details(),
            metadata=request.metadata + (("provider", "kubernetes"),),
        )

    def cleanup(
        self,
        sandbox: SandboxHandleLike,
        request: SandboxCleanupRequestLike | None = None,
    ) -> object:
        executors = _executors_module()
        state = self._require_sandbox(sandbox)
        metadata: tuple[tuple[str, str], ...] = ()
        cleaned_at = sandbox.created_at
        if request is not None:
            self._require_request_match(sandbox, request)
            metadata = request.metadata
            cleaned_at = request.requested_at

        if state.launched:
            _ = self.control_plane.delete_job(
                state.manifest.tenant_boundary.namespace,
                state.manifest.job_name,
            )
        del self._sandboxes[sandbox.identity.resource_name]
        return executors.SandboxCleanupResult(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            cleaned=True,
            cleaned_at=cleaned_at,
            released_resources=(
                f"job/{state.manifest.tenant_boundary.namespace}/{state.manifest.job_name}",
            ),
            metadata=metadata + (("provider", "kubernetes"),),
        )

    def _require_sandbox(self, sandbox: SandboxHandleLike) -> _StoredSandbox:
        state = self._sandboxes.get(sandbox.identity.resource_name)
        if state is None:
            raise cast(
                Exception,
                cast(object, _domain_module().InternalError("unknown sandbox handle")),
            )
        if state.sandbox != sandbox:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().InternalError(
                        "sandbox handle does not match stored executor state"
                    ),
                ),
            )
        return state

    def _require_request_match(
        self,
        sandbox: SandboxHandleLike,
        request: SandboxLaunchRequestLike
        | SandboxCancellationRequestLike
        | SandboxCleanupRequestLike,
    ) -> None:
        if request.tenant_id != sandbox.tenant_id:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().InternalError(
                        "sandbox request tenant must match handle"
                    ),
                ),
            )
        if request.request_id != sandbox.request_id:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().InternalError(
                        "sandbox request id must match handle"
                    ),
                ),
            )
        if request.job_id != sandbox.job_id:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().InternalError("sandbox job id must match handle"),
                ),
            )
        if request.identity != sandbox.identity:
            raise cast(
                Exception,
                cast(
                    object,
                    _domain_module().InternalError(
                        "sandbox identity must match handle identity"
                    ),
                ),
            )

    def _inspection_from_observation(
        self,
        sandbox: SandboxHandleLike,
        observation: KubernetesJobObservation,
    ) -> object:
        executors = _executors_module()
        status = self._status_from_phase(observation.phase, observation.error)
        details = self._error_details_for_observation(observation, status)
        return executors.SandboxInspection(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            status=status,
            observed_at=observation.observed_at,
            started_at=observation.started_at,
            finished_at=observation.finished_at,
            cancellation_requested_at=observation.cancellation_requested_at,
            deadline_at=sandbox.created_at
            + timedelta(seconds=sandbox.timeouts.execution_timeout_seconds),
            exit_code=observation.exit_code,
            error=details,
            metadata=(("provider", "kubernetes"),),
        )

    def _status_from_phase(
        self, phase: KubernetesJobPhase, error: object | None
    ) -> object:
        executors = _executors_module()
        if phase == KubernetesJobPhase.PENDING:
            return executors.SandboxStatus.PENDING
        if phase == KubernetesJobPhase.RUNNING:
            return executors.SandboxStatus.RUNNING
        if phase == KubernetesJobPhase.SUCCEEDED:
            return executors.SandboxStatus.SUCCEEDED
        if phase == KubernetesJobPhase.TIMED_OUT:
            return executors.SandboxStatus.TIMED_OUT
        if phase == KubernetesJobPhase.CANCELLED:
            return executors.SandboxStatus.CANCELLED
        if phase == KubernetesJobPhase.FAILED:
            if error is not None and hasattr(error, "category"):
                return executors.status_for_error(cast(ErrorDetailsLike, error))
            return executors.SandboxStatus.FAILED
        return executors.SandboxStatus.UNKNOWN

    def _error_details_for_observation(
        self,
        observation: KubernetesJobObservation,
        status: object,
    ) -> ErrorDetailsLike | None:
        domain = _domain_module()
        executors = _executors_module()
        if observation.error is not None:
            return cast(ErrorDetailsLike, observation.error)
        if status == executors.SandboxStatus.FAILED:
            return domain.RuntimeExecutionError(
                observation.message or "kubernetes job failed"
            ).as_details()
        if status == executors.SandboxStatus.TIMED_OUT:
            return domain.TimeoutError(
                observation.message or "kubernetes job exceeded its deadline"
            ).as_details()
        if status == executors.SandboxStatus.CANCELLED:
            return domain.CancellationError(
                observation.message or "kubernetes job was cancelled"
            ).as_details()
        return None

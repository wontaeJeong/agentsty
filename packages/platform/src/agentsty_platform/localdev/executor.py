"""Explicit local-development sandbox executor using host processes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config.settings import ExecutorSettings
from ..domain.errors import CancellationError, InternalError, RuntimeExecutionError
from ..executors.contracts import (
    SandboxCancellationReceipt,
    SandboxCancellationRequest,
    SandboxCapabilities,
    SandboxCleanupRequest,
    SandboxCleanupResult,
    SandboxCreateRequest,
    SandboxHandle,
    SandboxInspection,
    SandboxIsolationMode,
    SandboxLaunchReceipt,
    SandboxLaunchRequest,
    SandboxProgramSpec,
    SandboxResourceIdentity,
    SandboxStatus,
    TenantResourceBoundary,
    status_for_error,
)

LOCAL_DEVELOPMENT_EXECUTOR_NAME = "local-process"
LOCAL_RUNNER_MODULE = "agentsty_platform.runner"
_ALLOWED_ENVIRONMENT_KEYS = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONPATH",
    "TMPDIR",
    "VIRTUAL_ENV",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _resource_name(job_id: object) -> str:
    return f"local-runner-{_scoped_job_key(job_id).replace(':', '-')}"


def _scoped_job_key(job_id: object) -> str:
    scoped_value = getattr(job_id, "scoped_value", None)
    if isinstance(scoped_value, str):
        return scoped_value
    value = getattr(job_id, "value", None)
    if not isinstance(value, str):
        raise RuntimeExecutionError("job id must expose a string value")
    return value


def _minimal_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in _ALLOWED_ENVIRONMENT_KEYS:
        value = os.environ.get(key)
        if value is not None:
            environment[key] = value
    environment["PYTHONUNBUFFERED"] = "1"
    environment["AGENTSTY_SANDBOX_MODE"] = "local_development"
    return environment


def build_local_runner_program(
    *, environment: tuple[tuple[str, str], ...] = ()
) -> SandboxProgramSpec:
    """Build the real local runner program for host-process execution."""

    return SandboxProgramSpec(
        command=(sys.executable,),
        args=("-m", LOCAL_RUNNER_MODULE, "serve"),
        environment=environment,
    )


def build_packaged_runner_program(
    *,
    image_reference: str,
    environment: tuple[tuple[str, str], ...] = (),
) -> SandboxProgramSpec:
    """Build the packaged runner program for sandbox images."""

    return SandboxProgramSpec(
        command=("python",),
        args=("-m", LOCAL_RUNNER_MODULE, "serve"),
        environment=environment,
        working_directory="/workspace",
        image_reference=image_reference,
    )


@dataclass(slots=True)
class _StoredSandbox:
    sandbox: SandboxHandle
    working_directory: Path
    process: subprocess.Popen[bytes] | None = None
    started_at: datetime | None = None
    cancellation_requested_at: datetime | None = None


@dataclass(slots=True)
class LocalProcessSandboxExecutor:
    """Run sandbox entrypoints as honest local-development host processes."""

    executor_settings: ExecutorSettings
    workspace_root: Path
    _sandboxes: dict[str, _StoredSandbox] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.executor_settings.backend != "local":
            raise ValueError("local process executor requires executor.backend='local'")
        if self.executor_settings.isolation_mode != "process":
            raise ValueError(
                "local process executor requires executor.isolation_mode='process'"
            )

    @property
    def executor_name(self) -> str:
        return LOCAL_DEVELOPMENT_EXECUTOR_NAME

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            supported_isolation_modes=(SandboxIsolationMode.PROCESS,),
            tenant_boundary_kind="host-process",
            supports_status_inspection=True,
            supports_cancellation=True,
            supports_cleanup=True,
            supports_separate_launch_phase=True,
        )

    def create(self, request: SandboxCreateRequest) -> SandboxHandle:
        if request.desired_isolation is not SandboxIsolationMode.PROCESS:
            raise RuntimeExecutionError(
                "local development execution only supports host-process isolation"
            )

        working_directory = (
            self.workspace_root
            / "sandboxes"
            / request.tenant_id.value
            / request.job_id.value
        )
        working_directory.mkdir(parents=True, exist_ok=True)

        boundary = TenantResourceBoundary(
            tenant_id=request.tenant_id,
            boundary_kind=self.capabilities.tenant_boundary_kind,
            boundary_name=str(working_directory),
            metadata=(
                ("execution_mode", "local_development"),
                ("isolation_guarantee", "host_process_only"),
            ),
        )
        identity = SandboxResourceIdentity(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            executor_name=self.executor_name,
            provider="local",
            resource_kind="process",
            resource_name=_resource_name(request.job_id),
            boundary=boundary,
            metadata=request.metadata + (("execution_mode", "local_development"),),
        )
        sandbox = SandboxHandle(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            executor_name=self.executor_name,
            identity=identity,
            program=request.program,
            resources=request.resources,
            timeouts=request.timeouts,
            desired_isolation=request.desired_isolation,
            metadata=request.metadata
            + (
                ("execution_mode", "local_development"),
                ("isolation_guarantee", "host_process_only"),
            ),
        )
        self._sandboxes[_scoped_job_key(sandbox.job_id)] = _StoredSandbox(
            sandbox=sandbox,
            working_directory=working_directory,
        )
        return sandbox

    def launch(
        self,
        sandbox: SandboxHandle,
        request: SandboxLaunchRequest | None = None,
    ) -> SandboxLaunchReceipt:
        stored = self._require_stored_sandbox(sandbox)
        if stored.process is not None and stored.process.poll() is None:
            raise RuntimeExecutionError("sandbox process has already been launched")

        launch_request = request or SandboxLaunchRequest(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
        )
        self._require_request_match(sandbox, launch_request)
        environment = _minimal_environment()
        environment.update(sandbox.program.environment)

        command = sandbox.program.command + sandbox.program.args
        working_directory = self._resolve_working_directory(sandbox, stored)

        try:
            process = subprocess.Popen(
                command,
                cwd=working_directory,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise InternalError(
                f"failed to launch local sandbox process: {error}"
            ) from error

        started_at = _utc_now()
        stored.process = process
        stored.started_at = started_at
        return SandboxLaunchReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            accepted_at=started_at,
            deadline_at=started_at,
            metadata=launch_request.metadata
            + (("execution_mode", "local_development"),),
        )

    def inspect(self, sandbox: SandboxHandle) -> SandboxInspection:
        stored = self._require_stored_sandbox(sandbox)
        if stored.process is None or stored.started_at is None:
            return SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=SandboxStatus.CREATED,
                observed_at=_utc_now(),
                metadata=(("execution_mode", "local_development"),),
            )

        observed_at = _utc_now()
        return_code = stored.process.poll()
        if return_code is None:
            status = (
                SandboxStatus.CANCELLING
                if stored.cancellation_requested_at is not None
                else SandboxStatus.RUNNING
            )
            return SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=status,
                observed_at=observed_at,
                started_at=stored.started_at,
                cancellation_requested_at=stored.cancellation_requested_at,
                metadata=(("execution_mode", "local_development"),),
            )

        if stored.cancellation_requested_at is not None:
            error = CancellationError(
                "local sandbox execution was cancelled"
            ).as_details()
            return SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=SandboxStatus.CANCELLED,
                observed_at=observed_at,
                started_at=stored.started_at,
                finished_at=observed_at,
                cancellation_requested_at=stored.cancellation_requested_at,
                exit_code=return_code,
                error=error,
                metadata=(("execution_mode", "local_development"),),
            )

        if return_code == 0:
            return SandboxInspection(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                status=SandboxStatus.SUCCEEDED,
                observed_at=observed_at,
                started_at=stored.started_at,
                finished_at=observed_at,
                exit_code=return_code,
                metadata=(("execution_mode", "local_development"),),
            )

        error = RuntimeExecutionError(
            f"local sandbox process exited with code {return_code}"
        ).as_details()
        return SandboxInspection(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            status=status_for_error(error),
            observed_at=observed_at,
            started_at=stored.started_at,
            finished_at=observed_at,
            exit_code=return_code,
            error=error,
            metadata=(("execution_mode", "local_development"),),
        )

    def request_cancellation(
        self,
        sandbox: SandboxHandle,
        request: SandboxCancellationRequest,
    ) -> SandboxCancellationReceipt:
        stored = self._require_stored_sandbox(sandbox)
        self._require_request_match(sandbox, request)
        if stored.process is None or stored.started_at is None:
            error = RuntimeExecutionError(
                "sandbox process has not been launched for cancellation"
            ).as_details()
            return SandboxCancellationReceipt(
                tenant_id=sandbox.tenant_id,
                request_id=sandbox.request_id,
                job_id=sandbox.job_id,
                identity=sandbox.identity,
                acknowledged=False,
                requested_at=request.requested_at,
                error=error,
                metadata=request.metadata + (("execution_mode", "local_development"),),
            )

        if stored.process.poll() is None:
            stored.cancellation_requested_at = request.requested_at
            self._terminate_process(stored.process)

        return SandboxCancellationReceipt(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            acknowledged=True,
            requested_at=request.requested_at,
            metadata=request.metadata + (("execution_mode", "local_development"),),
        )

    def cleanup(
        self,
        sandbox: SandboxHandle,
        request: SandboxCleanupRequest | None = None,
    ) -> SandboxCleanupResult:
        stored = self._require_stored_sandbox(sandbox)
        process = stored.process
        if request is not None:
            self._require_request_match(sandbox, request)
        if process is not None and process.poll() is None:
            self._terminate_process(process)
            self._wait_for_exit(process)

        shutil.rmtree(stored.working_directory, ignore_errors=True)
        del self._sandboxes[_scoped_job_key(sandbox.job_id)]
        cleanup_request = request or SandboxCleanupRequest(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
        )
        return SandboxCleanupResult(
            tenant_id=sandbox.tenant_id,
            request_id=sandbox.request_id,
            job_id=sandbox.job_id,
            identity=sandbox.identity,
            cleaned=True,
            cleaned_at=_utc_now(),
            released_resources=(
                str(stored.working_directory),
                f"pid:{process.pid}" if process is not None else "process:not-started",
            ),
            metadata=cleanup_request.metadata
            + (
                ("execution_mode", "local_development"),
                ("isolation_guarantee", "host_process_only"),
            ),
        )

    def _require_stored_sandbox(self, sandbox: SandboxHandle) -> _StoredSandbox:
        stored = self._sandboxes.get(_scoped_job_key(sandbox.job_id))
        if stored is None:
            raise RuntimeExecutionError("unknown local sandbox handle")
        if stored.sandbox != sandbox:
            raise RuntimeExecutionError("sandbox handle does not match stored state")
        return stored

    def _resolve_working_directory(
        self,
        sandbox: SandboxHandle,
        stored: _StoredSandbox,
    ) -> Path:
        if sandbox.program.working_directory is None:
            return stored.working_directory
        working_directory = Path(sandbox.program.working_directory).resolve()
        sandbox_root = stored.working_directory.resolve()
        if sandbox_root not in (working_directory, *working_directory.parents):
            raise RuntimeExecutionError(
                "local sandbox working_directory must stay within the sandbox workspace"
            )
        working_directory.mkdir(parents=True, exist_ok=True)
        return working_directory

    def _require_request_match(
        self,
        sandbox: SandboxHandle,
        request: SandboxLaunchRequest
        | SandboxCancellationRequest
        | SandboxCleanupRequest,
    ) -> None:
        if request.tenant_id != sandbox.tenant_id:
            raise RuntimeExecutionError("sandbox request tenant must match handle")
        if request.request_id != sandbox.request_id:
            raise RuntimeExecutionError("sandbox request id must match handle")
        if request.job_id != sandbox.job_id:
            raise RuntimeExecutionError("sandbox job id must match handle")
        if request.identity != sandbox.identity:
            raise RuntimeExecutionError("sandbox identity must match handle identity")

    def _terminate_process(self, process: subprocess.Popen[bytes]) -> None:
        try:
            process.terminate()
        except ProcessLookupError:
            return

    def _wait_for_exit(self, process: subprocess.Popen[bytes]) -> None:
        try:
            _ = process.wait(timeout=2.0)
            return
        except subprocess.TimeoutExpired:
            pass
        except ChildProcessError:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        try:
            _ = process.wait(timeout=2.0)
        except (ChildProcessError, subprocess.TimeoutExpired):
            return

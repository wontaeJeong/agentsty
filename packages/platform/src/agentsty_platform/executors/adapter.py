"""Protocol for pluggable sandbox executor adapters."""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    SandboxCancellationReceipt,
    SandboxCancellationRequest,
    SandboxCapabilities,
    SandboxCleanupRequest,
    SandboxCleanupResult,
    SandboxCreateRequest,
    SandboxHandle,
    SandboxInspection,
    SandboxLaunchReceipt,
    SandboxLaunchRequest,
)


class SandboxExecutor(Protocol):
    """Lifecycle contract implemented by concrete sandbox executors."""

    @property
    def executor_name(self) -> str: ...

    @property
    def capabilities(self) -> SandboxCapabilities: ...

    def create(self, request: SandboxCreateRequest) -> SandboxHandle: ...

    def launch(
        self,
        sandbox: SandboxHandle,
        request: SandboxLaunchRequest | None = None,
    ) -> SandboxLaunchReceipt: ...

    def inspect(self, sandbox: SandboxHandle) -> SandboxInspection: ...

    def request_cancellation(
        self,
        sandbox: SandboxHandle,
        request: SandboxCancellationRequest,
    ) -> SandboxCancellationReceipt: ...

    def cleanup(
        self,
        sandbox: SandboxHandle,
        request: SandboxCleanupRequest | None = None,
    ) -> SandboxCleanupResult: ...

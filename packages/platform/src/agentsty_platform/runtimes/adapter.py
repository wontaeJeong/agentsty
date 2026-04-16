"""Protocol for pluggable agent runtime adapters."""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    RuntimeCancellationReceipt,
    RuntimeCancellationRequest,
    RuntimeCapabilities,
    RuntimeCleanupRequest,
    RuntimeCleanupResult,
    RuntimeCollectionRequest,
    RuntimeCollectionResult,
    RuntimeInvocationReceipt,
    RuntimeInvocationRequest,
    RuntimePreparationRequest,
    RuntimeSession,
)


class AgentRuntimeAdapter(Protocol):
    """Lifecycle contract implemented by concrete headless agent runtimes."""

    @property
    def runtime_name(self) -> str: ...

    @property
    def capabilities(self) -> RuntimeCapabilities: ...

    def prepare(self, request: RuntimePreparationRequest) -> RuntimeSession: ...

    def invoke(
        self,
        session: RuntimeSession,
        request: RuntimeInvocationRequest,
    ) -> RuntimeInvocationReceipt: ...

    def collect_result(
        self,
        session: RuntimeSession,
        request: RuntimeCollectionRequest | None = None,
    ) -> RuntimeCollectionResult: ...

    def request_cancellation(
        self,
        session: RuntimeSession,
        request: RuntimeCancellationRequest,
    ) -> RuntimeCancellationReceipt: ...

    def cleanup(
        self,
        session: RuntimeSession,
        request: RuntimeCleanupRequest | None = None,
    ) -> RuntimeCleanupResult: ...

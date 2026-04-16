"""Runtime boundary for pluggable agent runtime contracts and adapters."""

from __future__ import annotations

from importlib import import_module
from typing import cast

AgentRuntimeAdapter: object
build_runtime_adapter: object
build_runtime_adapter_from_env: object
runtime_factory_kwargs_from_env: object
RuntimeAutomationMode: object
RuntimeCancellationReceipt: object
RuntimeCancellationRequest: object
RuntimeCapabilities: object
RuntimeCleanupRequest: object
RuntimeCleanupResult: object
RuntimeCollectionRequest: object
RuntimeCollectionResult: object
RuntimeInvocationReceipt: object
RuntimeInvocationRequest: object
RuntimePreparationRequest: object
RuntimeSession: object
status_for_error: object

_CONTRACT_EXPORTS = {
    "RuntimeAutomationMode",
    "RuntimeCancellationReceipt",
    "RuntimeCancellationRequest",
    "RuntimeCapabilities",
    "RuntimeCleanupRequest",
    "RuntimeCleanupResult",
    "RuntimeCollectionRequest",
    "RuntimeCollectionResult",
    "RuntimeInvocationReceipt",
    "RuntimeInvocationRequest",
    "RuntimePreparationRequest",
    "RuntimeSession",
    "status_for_error",
}

__all__ = [
    "AgentRuntimeAdapter",
    "build_runtime_adapter",
    "build_runtime_adapter_from_env",
    "runtime_factory_kwargs_from_env",
    "RuntimeAutomationMode",
    "RuntimeCancellationReceipt",
    "RuntimeCancellationRequest",
    "RuntimeCapabilities",
    "RuntimeCleanupRequest",
    "RuntimeCleanupResult",
    "RuntimeCollectionRequest",
    "RuntimeCollectionResult",
    "RuntimeInvocationReceipt",
    "RuntimeInvocationRequest",
    "RuntimePreparationRequest",
    "RuntimeSession",
    "status_for_error",
]


def __getattr__(name: str) -> object:
    """Lazily expose runtime symbols without eager package-local imports."""

    if name == "AgentRuntimeAdapter":
        return cast(
            object,
            import_module("agentsty_platform.runtimes.adapter").AgentRuntimeAdapter,
        )
    if name in {
        "build_runtime_adapter",
        "build_runtime_adapter_from_env",
        "runtime_factory_kwargs_from_env",
    }:
        return cast(
            object,
            getattr(import_module("agentsty_platform.runtimes.factory"), name),
        )
    if name in _CONTRACT_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.runtimes.contracts"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

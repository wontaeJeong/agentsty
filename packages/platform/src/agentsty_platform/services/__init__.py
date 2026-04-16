"""Service boundary for orchestration and platform coordination logic."""

from __future__ import annotations

from importlib import import_module
from typing import cast

CleanupCoordinator: object
CleanupOutcome: object
ExecutionCancellationRequest: object
ExecutionCancellationResult: object
ExecutionOrchestrator: object
ExecutionPollResult: object
ExecutionSubmitRequest: object
ExecutionSubmitResult: object
InMemoryPolicyQuotaService: object
PolicyQuotaDecision: object
PolicyQuotaService: object
RequestIntakeResult: object
RequestIntakeService: object

_MODEL_EXPORTS = {
    "ExecutionCancellationRequest",
    "ExecutionCancellationResult",
    "ExecutionPollResult",
    "ExecutionSubmitRequest",
    "ExecutionSubmitResult",
}
_POLICY_EXPORTS = {
    "InMemoryPolicyQuotaService",
    "PolicyQuotaDecision",
    "PolicyQuotaService",
}
_INTAKE_EXPORTS = {
    "RequestIntakeResult",
    "RequestIntakeService",
}
_CLEANUP_EXPORTS = {
    "CleanupCoordinator",
    "CleanupOutcome",
}

__all__ = [
    "CleanupCoordinator",
    "CleanupOutcome",
    "ExecutionCancellationRequest",
    "ExecutionCancellationResult",
    "ExecutionOrchestrator",
    "ExecutionPollResult",
    "ExecutionSubmitRequest",
    "ExecutionSubmitResult",
    "InMemoryPolicyQuotaService",
    "PolicyQuotaDecision",
    "PolicyQuotaService",
    "RequestIntakeResult",
    "RequestIntakeService",
]


def __getattr__(name: str) -> object:
    """Lazily expose service symbols without eager package-local imports."""

    if name in _MODEL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.services.models"), name),
        )
    if name in _POLICY_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.services.policy"), name),
        )
    if name in _INTAKE_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.services.intake"), name),
        )
    if name in _CLEANUP_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.services.cleanup"), name),
        )
    if name == "ExecutionOrchestrator":
        return cast(
            object,
            getattr(import_module("agentsty_platform.services.orchestration"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

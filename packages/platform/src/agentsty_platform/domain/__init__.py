"""Domain boundary for shared models, contracts, and error types."""

from __future__ import annotations

from importlib import import_module
from typing import cast

ArtifactPersistenceError: object
ArtifactSummary: object
AuthenticationError: object
AuthorizationError: object
CancellationError: object
CancellationState: object
DomainError: object
ErrorCategory: object
ErrorDetails: object
ExecutionRequest: object
ExecutionResult: object
ExecutionState: object
ExecutionStatus: object
ExecutionTimeouts: object
GatewayError: object
IdempotencyKey: object
InternalError: object
InvalidRequestError: object
JobId: object
PolicyViolationError: object
QuotaExceededError: object
RequestId: object
ResultSummary: object
RuntimeExecutionError: object
SandboxCreationError: object
TenantId: object
TimeoutError: object
TimeoutState: object
UnknownError: object

_IDS_EXPORTS = {
    "IdempotencyKey",
    "JobId",
    "RequestId",
    "TenantId",
}
_MODELS_EXPORTS = {
    "ArtifactSummary",
    "ExecutionTimeouts",
    "ResultSummary",
}
_ERROR_EXPORTS = {
    "ArtifactPersistenceError",
    "AuthenticationError",
    "AuthorizationError",
    "CancellationError",
    "DomainError",
    "ErrorCategory",
    "ErrorDetails",
    "GatewayError",
    "InternalError",
    "InvalidRequestError",
    "PolicyViolationError",
    "QuotaExceededError",
    "RuntimeExecutionError",
    "SandboxCreationError",
    "TimeoutError",
    "UnknownError",
}
_EXECUTION_EXPORTS = {
    "CancellationState",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionState",
    "ExecutionStatus",
    "TimeoutState",
}

__all__ = [
    "ArtifactPersistenceError",
    "ArtifactSummary",
    "AuthenticationError",
    "AuthorizationError",
    "CancellationError",
    "CancellationState",
    "DomainError",
    "ErrorCategory",
    "ErrorDetails",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionState",
    "ExecutionStatus",
    "ExecutionTimeouts",
    "GatewayError",
    "IdempotencyKey",
    "InternalError",
    "InvalidRequestError",
    "JobId",
    "PolicyViolationError",
    "QuotaExceededError",
    "RequestId",
    "ResultSummary",
    "RuntimeExecutionError",
    "SandboxCreationError",
    "TenantId",
    "TimeoutError",
    "TimeoutState",
    "UnknownError",
]


def __getattr__(name: str) -> object:
    """Lazily expose domain symbols without eager package-local imports."""

    if name in _IDS_EXPORTS:
        return cast(
            object, getattr(import_module("agentsty_platform.domain.ids"), name)
        )
    if name in _MODELS_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.domain.models"), name),
        )
    if name in _ERROR_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.domain.errors"), name),
        )
    if name in _EXECUTION_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.domain.execution"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

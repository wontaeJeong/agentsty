"""Stable domain error taxonomy shared across services and adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .models import Metadata, normalize_metadata


class ErrorCategory(StrEnum):
    """Stable platform error categories for later transport mapping."""

    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    POLICY_VIOLATION = "policy_violation"
    QUOTA_EXCEEDED = "quota_exceeded"
    SANDBOX_CREATION_FAILURE = "sandbox_creation_failure"
    RUNTIME_FAILURE = "runtime_failure"
    GATEWAY_FAILURE = "gateway_failure"
    ARTIFACT_PERSISTENCE_FAILURE = "artifact_persistence_failure"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ErrorDetails:
    """Serializable error contract for persistence, services, and APIs."""

    category: ErrorCategory
    message: str
    code: str | None = None
    retryable: bool = False
    metadata: Metadata = field(default_factory=tuple)

    def __post_init__(self) -> None:
        clean_message = self.message.strip()
        if not clean_message:
            raise ValueError("error message must not be empty")
        object.__setattr__(self, "message", clean_message)
        object.__setattr__(self, "code", self.code or self.category.value)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


class DomainError(Exception):
    """Base exception carrying stable domain error metadata."""

    category: ErrorCategory = ErrorCategory.INTERNAL
    default_retryable: bool = False
    details: ErrorDetails

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        metadata: Metadata = (),
    ) -> None:
        super().__init__(message)
        self.details = ErrorDetails(
            category=self.category,
            message=message,
            code=code,
            retryable=(self.default_retryable if retryable is None else retryable),
            metadata=metadata,
        )

    def as_details(self) -> ErrorDetails:
        return self.details


class InvalidRequestError(DomainError):
    category: ErrorCategory = ErrorCategory.INVALID_REQUEST


class AuthenticationError(DomainError):
    category: ErrorCategory = ErrorCategory.AUTHENTICATION


class AuthorizationError(DomainError):
    category: ErrorCategory = ErrorCategory.AUTHORIZATION


class PolicyViolationError(DomainError):
    category: ErrorCategory = ErrorCategory.POLICY_VIOLATION


class QuotaExceededError(DomainError):
    category: ErrorCategory = ErrorCategory.QUOTA_EXCEEDED


class SandboxCreationError(DomainError):
    category: ErrorCategory = ErrorCategory.SANDBOX_CREATION_FAILURE
    default_retryable: bool = True


class RuntimeExecutionError(DomainError):
    category: ErrorCategory = ErrorCategory.RUNTIME_FAILURE


class GatewayError(DomainError):
    category: ErrorCategory = ErrorCategory.GATEWAY_FAILURE
    default_retryable: bool = True


class ArtifactPersistenceError(DomainError):
    category: ErrorCategory = ErrorCategory.ARTIFACT_PERSISTENCE_FAILURE


class TimeoutError(DomainError):
    category: ErrorCategory = ErrorCategory.TIMEOUT


class CancellationError(DomainError):
    category: ErrorCategory = ErrorCategory.CANCELLATION


class InternalError(DomainError):
    category: ErrorCategory = ErrorCategory.INTERNAL


class UnknownError(DomainError):
    category: ErrorCategory = ErrorCategory.UNKNOWN

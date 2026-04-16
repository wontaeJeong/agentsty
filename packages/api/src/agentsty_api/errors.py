"""HTTP-facing error mapping over the shared domain taxonomy."""

# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .schemas import ErrorEnvelope, ErrorResponseBody


class ErrorDetailsLike(Protocol):
    category: object
    message: str
    code: str | None
    retryable: bool
    metadata: tuple[tuple[str, str], ...]


@dataclass(slots=True)
class APIError(Exception):
    """Normalized HTTP error carrying shared error details."""

    status_code: int
    details: ErrorDetailsLike
    tenant_id: str | None = None
    request_id: str | None = None
    job_id: str | None = None


_STATUS_BY_CATEGORY: dict[str, int] = {
    "invalid_request": 400,
    "authentication": 401,
    "authorization": 403,
    "policy_violation": 403,
    "quota_exceeded": 429,
    "sandbox_creation_failure": 502,
    "runtime_failure": 502,
    "gateway_failure": 502,
    "artifact_persistence_failure": 500,
    "timeout": 504,
    "cancellation": 409,
    "internal": 500,
    "unknown": 500,
}


def map_error_details(
    details: ErrorDetailsLike,
    *,
    tenant_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> APIError:
    """Map shared error details to an HTTP-facing exception."""

    category = str(details.category)
    return APIError(
        status_code=_STATUS_BY_CATEGORY.get(category, 500),
        details=details,
        tenant_id=tenant_id,
        request_id=request_id,
        job_id=job_id,
    )


def error_body(details: ErrorDetailsLike) -> ErrorResponseBody:
    return ErrorResponseBody(
        message=details.message,
        category=str(details.category),
        code=details.code or str(details.category),
        retryable=details.retryable,
        metadata={key: value for key, value in details.metadata},
    )


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    """Render normalized API errors as stable JSON envelopes."""

    envelope = ErrorEnvelope(
        error=error_body(exc.details),
        tenant_id=exc.tenant_id,
        request_id=exc.request_id,
        job_id=exc.job_id,
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    """Normalize FastAPI validation failures into the shared invalid-request shape."""

    entries = tuple(
        ("/".join(str(part) for part in error["loc"]), error["msg"])
        for error in exc.errors()
    )
    body = ErrorEnvelope(
        error=ErrorResponseBody(
            message="request validation failed",
            category="invalid_request",
            code="invalid_request",
            retryable=False,
            metadata={key: value for key, value in entries},
        )
    )
    return JSONResponse(status_code=400, content=body.model_dump())

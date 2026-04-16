"""FastAPI application factory for the north-south API surface."""

# pyright: reportMissingImports=false

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .dependencies import APIDependencies, create_default_dependencies
from .errors import APIError, api_error_handler, validation_error_handler
from .routes import router


def create_app(dependencies: APIDependencies | None = None) -> FastAPI:
    """Create the FastAPI app with transport-only wiring over shared services."""

    resolved_dependencies = dependencies or create_default_dependencies()
    app = FastAPI(title="agentsty-api")
    app.state.agentsty_dependencies = resolved_dependencies
    app.add_exception_handler(APIError, cast(Any, api_error_handler))
    app.add_exception_handler(
        RequestValidationError, cast(Any, validation_error_handler)
    )
    app.include_router(router)
    return app

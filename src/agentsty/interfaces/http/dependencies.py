from typing import cast

from fastapi import Request

from agentsty.application.services.execution_service import ExecutionService


def get_execution_service(request: Request) -> ExecutionService:
    return cast(ExecutionService, request.app.state.execution_service)

from functools import lru_cache

from agentsty.application.services.execution_service import ExecutionService
from agentsty.bootstrap import build_execution_service


@lru_cache(maxsize=1)
def get_execution_service() -> ExecutionService:
    return build_execution_service()

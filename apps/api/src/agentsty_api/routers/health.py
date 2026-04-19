from agentsty_common.health import HealthResponse
from fastapi import APIRouter

from ..settings import ApiSettings

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = ApiSettings()
    return HealthResponse(service=settings.service_kind, version=settings.version)

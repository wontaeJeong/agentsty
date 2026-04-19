from agentsty_common.health import HealthResponse
from fastapi import APIRouter

from ..settings import ProxySettings

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = ProxySettings()
    return HealthResponse(service=settings.service_kind, version=settings.version)

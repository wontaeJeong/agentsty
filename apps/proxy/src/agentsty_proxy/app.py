from fastapi import FastAPI

from .routers.health import router as health_router
from .routers.providers import router as providers_router
from .settings import ProxySettings


def create_app() -> FastAPI:
    settings = ProxySettings()
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health_router)
    app.include_router(providers_router)
    return app

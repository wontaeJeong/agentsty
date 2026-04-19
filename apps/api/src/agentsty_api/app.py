from fastapi import FastAPI

from .routers.health import router as health_router
from .routers.runs import router as runs_router
from .settings import ApiSettings


def create_app() -> FastAPI:
    settings = ApiSettings()
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health_router)
    app.include_router(runs_router)
    return app

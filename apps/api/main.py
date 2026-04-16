from fastapi import FastAPI

from agentsty.interfaces.http.routes.chat_completions import router as chat_completions_router
from agentsty.interfaces.http.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="agentsty", version="0.1.0")
    app.include_router(health_router)
    app.include_router(chat_completions_router)
    return app


app = create_app()

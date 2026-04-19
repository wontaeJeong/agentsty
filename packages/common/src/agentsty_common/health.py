from pydantic import BaseModel

from .enums import ServiceKind


class HealthResponse(BaseModel):
    status: str = "ok"
    service: ServiceKind
    version: str

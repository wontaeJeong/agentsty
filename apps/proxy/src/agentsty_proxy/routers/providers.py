from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderProxyStatus(BaseModel):
    mediated: bool
    detail: str


@router.get("/status", response_model=ProviderProxyStatus)
def provider_status() -> ProviderProxyStatus:
    return ProviderProxyStatus(
        mediated=True,
        detail=(
            "Provider mediation placeholder. Secret resolution and upstream calls are not "
            "implemented yet."
        ),
    )

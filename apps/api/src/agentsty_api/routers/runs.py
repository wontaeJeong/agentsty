from uuid import UUID

from agentsty_common.enums import RunStatus
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/runs", tags=["runs"])


class RunLifecycleResponse(BaseModel):
    run_id: UUID
    status: RunStatus
    detail: str


@router.post("/{run_id}", response_model=RunLifecycleResponse)
def submit_run(run_id: UUID) -> RunLifecycleResponse:
    return RunLifecycleResponse(
        run_id=run_id,
        status=RunStatus.QUEUED,
        detail="Run lifecycle endpoint placeholder. Orchestration service not implemented yet.",
    )

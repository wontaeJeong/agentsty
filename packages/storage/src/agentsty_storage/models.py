from agentsty_common.enums import RunStatus
from agentsty_common.ownership import OwnershipContext
from pydantic import BaseModel, Field


class SecretReference(BaseModel):
    secret_id: str
    purpose: str


class RunRecord(BaseModel):
    run_id: str
    ownership: OwnershipContext
    status: RunStatus = RunStatus.QUEUED
    agent_backend: str
    sandbox_backend: str


class ArtifactRecord(BaseModel):
    artifact_id: str
    run_id: str
    ownership: OwnershipContext
    path_hint: str | None = None
    media_type: str = Field(default="application/octet-stream")

from agentsty_common.ownership import OwnershipContext
from agentsty_storage.models import SecretReference
from pydantic import BaseModel, Field


class AgentBackendInfo(BaseModel):
    key: str
    display_name: str
    supports_tool_execution: bool = True


class AgentRunRequest(BaseModel):
    run_id: str
    ownership: OwnershipContext
    backend_key: str
    prompt: str
    secret_references: tuple[SecretReference, ...] = Field(default_factory=tuple)


class AgentRunResult(BaseModel):
    run_id: str
    backend_key: str
    output_text: str
    artifact_ids: tuple[str, ...] = Field(default_factory=tuple)

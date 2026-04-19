from agentsty_common.ownership import OwnershipContext
from agentsty_storage.models import SecretReference
from pydantic import BaseModel, Field


class NetworkPolicy(BaseModel):
    default_deny: bool = True
    allowlisted_hosts: tuple[str, ...] = Field(default_factory=tuple)


class SandboxPolicy(BaseModel):
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    writable_workspace: bool = False
    max_runtime_seconds: int = 300


class SandboxExecutionRequest(BaseModel):
    run_id: str
    ownership: OwnershipContext
    command: tuple[str, ...]
    policy: SandboxPolicy = Field(default_factory=SandboxPolicy)
    secret_references: tuple[SecretReference, ...] = Field(default_factory=tuple)


class SandboxExecutionResult(BaseModel):
    run_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""

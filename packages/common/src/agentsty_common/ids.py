from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
SessionId = NewType("SessionId", UUID)
JobId = NewType("JobId", UUID)
RunId = NewType("RunId", UUID)
SandboxId = NewType("SandboxId", UUID)
ArtifactId = NewType("ArtifactId", UUID)
AgentId = NewType("AgentId", str)
SecretRefId = NewType("SecretRefId", str)

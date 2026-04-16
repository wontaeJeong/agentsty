from __future__ import annotations

from dataclasses import dataclass, field
from typing import NewType

type JSONScalar = str | int | float | bool | None
type Metadata = dict[str, JSONScalar]
TenantId = NewType("TenantId", str)


@dataclass(frozen=True)
class Artifact:
    name: str
    mime_type: str = "text/plain"
    uri: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    tenant_id: TenantId
    message: str
    metadata: Metadata | None
    timeout_seconds: int


@dataclass(frozen=True)
class PreparedExecution:
    request_id: str
    tenant_id: TenantId
    message: str
    metadata: Metadata
    timeout_seconds: int
    runtime_name: str


@dataclass(frozen=True)
class SandboxExecutionRecord:
    sandbox_execution_id: str
    status: str
    output_text: str
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionResult:
    request_id: str
    status: str
    generated_text: str
    artifacts: list[Artifact]
    runtime_name: str
    sandbox_execution_id: str


class SandboxExecutionError(RuntimeError):
    pass


class RuntimeExecutionError(RuntimeError):
    pass

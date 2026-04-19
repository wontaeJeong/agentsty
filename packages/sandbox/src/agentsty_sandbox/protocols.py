from typing import Protocol

from .models import SandboxExecutionRequest, SandboxExecutionResult


class SandboxBackend(Protocol):
    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult: ...

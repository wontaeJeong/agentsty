from typing import Protocol

from .models import AgentBackendInfo, AgentRunRequest, AgentRunResult


class AgentBackend(Protocol):
    @property
    def info(self) -> AgentBackendInfo: ...

    def execute(self, request: AgentRunRequest) -> AgentRunResult: ...

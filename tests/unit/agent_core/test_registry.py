import pytest
from agentsty_agent_core.errors import AgentAlreadyRegisteredError, AgentNotFoundError
from agentsty_agent_core.models import AgentBackendInfo, AgentRunRequest, AgentRunResult
from agentsty_agent_core.registry import AgentRegistry


class StubAgentBackend:
    @property
    def info(self) -> AgentBackendInfo:
        return AgentBackendInfo(key="stub", display_name="Stub Agent")

    def execute(self, request: AgentRunRequest) -> AgentRunResult:
        return AgentRunResult(run_id=request.run_id, backend_key="stub", output_text="ok")


def test_registry_registers_and_resolves_backend() -> None:
    registry = AgentRegistry()
    backend = StubAgentBackend()
    registry.register(backend)

    assert registry.resolve("stub") is backend


def test_registry_rejects_duplicate_registration() -> None:
    registry = AgentRegistry()
    backend = StubAgentBackend()
    registry.register(backend)

    with pytest.raises(AgentAlreadyRegisteredError):
        registry.register(backend)


def test_registry_raises_for_missing_backend() -> None:
    registry = AgentRegistry()

    with pytest.raises(AgentNotFoundError):
        registry.resolve("missing")

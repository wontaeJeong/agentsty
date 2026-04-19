from .errors import AgentAlreadyRegisteredError, AgentNotFoundError
from .protocols import AgentBackend


class AgentRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, AgentBackend] = {}

    def register(self, backend: AgentBackend) -> None:
        backend_key = backend.info.key
        if backend_key in self._backends:
            msg = f"Agent backend '{backend_key}' is already registered"
            raise AgentAlreadyRegisteredError(msg)
        self._backends[backend_key] = backend

    def resolve(self, backend_key: str) -> AgentBackend:
        backend = self._backends.get(backend_key)
        if backend is None:
            msg = f"Agent backend '{backend_key}' is not registered"
            raise AgentNotFoundError(msg)
        return backend

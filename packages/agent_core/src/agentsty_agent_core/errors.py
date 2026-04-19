class AgentRegistryError(Exception):
    """Base registry error."""


class AgentAlreadyRegisteredError(AgentRegistryError):
    """Raised when the same agent backend key is registered twice."""


class AgentNotFoundError(AgentRegistryError):
    """Raised when an agent backend cannot be resolved."""

from agentsty.application.services.execution_service import ExecutionService
from agentsty.infrastructure.config.settings import Settings, get_settings
from agentsty.infrastructure.executors.stub import StubSandboxExecutor
from agentsty.infrastructure.runtimes.opencode import OpenCodeRuntime


def build_execution_service(settings: Settings | None = None) -> ExecutionService:
    resolved_settings = settings or get_settings()

    if resolved_settings.default_runtime == "opencode":
        runtime = OpenCodeRuntime()
    else:
        msg = f"Unsupported runtime: {resolved_settings.default_runtime}"
        raise ValueError(msg)

    if resolved_settings.sandbox_mode == "stub":
        sandbox_executor = StubSandboxExecutor()
    else:
        msg = f"Unsupported sandbox mode: {resolved_settings.sandbox_mode}"
        raise ValueError(msg)

    return ExecutionService(runtime=runtime, sandbox_executor=sandbox_executor)

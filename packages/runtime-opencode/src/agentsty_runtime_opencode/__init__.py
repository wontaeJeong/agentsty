"""OpenCode runtime adapter package metadata."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Final, cast

OpenCodeRuntimeAdapter: object
OPENCODE_RUNTIME_NAME: object

__all__ = [
    "DISTRO_NAME",
    "create_runtime_adapter",
    "OPENCODE_RUNTIME_NAME",
    "OpenCodeRuntimeAdapter",
    "PACKAGE_NAME",
    "PLATFORM_RUNTIME_NAMESPACE",
    "__version__",
    "package_metadata",
    "runtime_factory_kwargs_from_env",
]

PACKAGE_NAME: Final[str] = "agentsty_runtime_opencode"
DISTRO_NAME: Final[str] = "agentsty-runtime-opencode"
PLATFORM_RUNTIME_NAMESPACE: Final[str] = "agentsty_platform.runtimes"
__version__: Final[str] = "0.0.0"


def package_metadata() -> dict[str, str]:
    """Return minimal runtime adapter identity metadata."""

    return {
        "package_name": PACKAGE_NAME,
        "distribution_name": DISTRO_NAME,
        "platform_runtime_namespace": PLATFORM_RUNTIME_NAMESPACE,
        "version": __version__,
    }


def create_runtime_adapter(
    *,
    gateway_client: object,
    runtime_settings: object,
    **kwargs: object,
) -> object:
    adapter_module = import_module("agentsty_runtime_opencode.adapter")
    return adapter_module.OpenCodeRuntimeAdapter(
        gateway_client=gateway_client,
        runtime_settings=runtime_settings,
        **kwargs,
    )


def runtime_factory_kwargs_from_env(
    environ: Mapping[str, str],
) -> dict[str, object]:
    env = dict(environ)
    if env.get("AGENTSTY_RUNNER_COMMAND_RUNNER") != "inline":
        return {}
    process_module = import_module("agentsty_runtime_opencode.process")
    return {
        "command_runner": cast(
            object,
            process_module.InlineCommandRunner.from_environment(env),
        )
    }


def __getattr__(name: str) -> object:
    """Lazily expose adapter symbols without eager package-local imports."""

    if name in {"OpenCodeRuntimeAdapter", "OPENCODE_RUNTIME_NAME"}:
        return getattr(import_module("agentsty_runtime_opencode.adapter"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

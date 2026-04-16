from __future__ import annotations

import importlib


def test_workspace_packages_import() -> None:
    for module_name in (
        "agentsty_platform",
        "agentsty_api",
        "agentsty_runtime_opencode",
        "agentsty_executor_kubernetes",
    ):
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name


def test_platform_boundary_packages_import() -> None:
    for module_name in (
        "agentsty_platform.config",
        "agentsty_platform.domain",
        "agentsty_platform.services",
        "agentsty_platform.gateway",
        "agentsty_platform.persistence",
        "agentsty_platform.observability",
        "agentsty_platform.executors",
        "agentsty_platform.runtimes",
    ):
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name

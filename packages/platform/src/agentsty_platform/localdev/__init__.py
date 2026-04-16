"""Local-development execution helpers and executor implementation."""

from __future__ import annotations

from importlib import import_module
from typing import cast

LocalProcessSandboxExecutor: object
LOCAL_DEVELOPMENT_EXECUTOR_NAME: object
LOCAL_RUNNER_MODULE: object
build_local_runner_program: object
build_packaged_runner_program: object

__all__ = [
    "LOCAL_DEVELOPMENT_EXECUTOR_NAME",
    "LOCAL_RUNNER_MODULE",
    "LocalProcessSandboxExecutor",
    "build_local_runner_program",
    "build_packaged_runner_program",
]


def __getattr__(name: str) -> object:
    """Lazily expose local-development helpers without eager imports."""

    if name in {
        "LocalProcessSandboxExecutor",
        "LOCAL_DEVELOPMENT_EXECUTOR_NAME",
        "LOCAL_RUNNER_MODULE",
        "build_local_runner_program",
        "build_packaged_runner_program",
    }:
        return cast(
            object,
            getattr(import_module("agentsty_platform.localdev.executor"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

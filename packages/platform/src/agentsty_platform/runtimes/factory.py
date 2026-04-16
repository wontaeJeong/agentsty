"""Composition helpers for pluggable runtime adapters."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Protocol, cast


class RuntimeSettingsLike(Protocol):
    backend: str


class SettingsLike(Protocol):
    runtime: RuntimeSettingsLike


class RuntimeEnvFactory(Protocol):
    def __call__(self, environ: Mapping[str, str]) -> Mapping[str, object]: ...


class RuntimeModuleLike(Protocol):
    def create_runtime_adapter(
        self,
        *,
        gateway_client: object,
        runtime_settings: object,
        **kwargs: object,
    ) -> object: ...


_RUNTIME_PACKAGE_OVERRIDES: dict[str, str] = {
    "opencode": "agentsty_runtime_opencode",
}


def _normalized_backend_name(settings: SettingsLike) -> str:
    backend = settings.runtime.backend.strip().lower().replace("-", "_")
    if not backend:
        raise ValueError("runtime backend must not be empty")
    return backend


def _runtime_module(settings: SettingsLike) -> RuntimeModuleLike:
    backend = _normalized_backend_name(settings)
    package_name = _RUNTIME_PACKAGE_OVERRIDES.get(
        backend, f"agentsty_runtime_{backend}"
    )
    module = import_module(package_name)
    if not hasattr(module, "create_runtime_adapter"):
        raise ValueError(
            f"runtime package {package_name!r} does not expose create_runtime_adapter()"
        )
    return cast(RuntimeModuleLike, cast(object, module))


def build_runtime_adapter(
    settings: SettingsLike,
    gateway_client: object,
    **kwargs: object,
) -> object:
    module = _runtime_module(settings)
    return module.create_runtime_adapter(
        gateway_client=gateway_client,
        runtime_settings=settings.runtime,
        **kwargs,
    )


def runtime_factory_kwargs_from_env(
    settings: SettingsLike,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = dict(environ or {})
    module = _runtime_module(settings)
    helper = getattr(module, "runtime_factory_kwargs_from_env", None)
    if helper is None:
        return {}
    return dict(cast(RuntimeEnvFactory, helper)(env))


def build_runtime_adapter_from_env(
    settings: SettingsLike,
    gateway_client: object,
    *,
    environ: Mapping[str, str] | None = None,
    **kwargs: object,
) -> object:
    env_kwargs = runtime_factory_kwargs_from_env(settings, environ)
    env_kwargs.update(kwargs)
    return build_runtime_adapter(settings, gateway_client, **env_kwargs)

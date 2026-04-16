from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest

if TYPE_CHECKING:

    class _APISettings(Protocol):
        bind_port: int

    class _GatewaySettings(Protocol):
        internal_only: bool
        require_tls: bool
        base_url: str

    class _ExecutorSettings(Protocol):
        backend: str
        isolation_mode: str

    class _RuntimeSettings(Protocol):
        workspace_root: Path
        sandbox_image_reference: str | None
        expose_vendor_credentials: bool

    class _AuthSettings(Protocol):
        required: bool
        mode: str
        audience: str | None
        allow_anonymous_local: bool

    class _TimeoutSettings(Protocol):
        request_timeout_seconds: int
        execution_timeout_seconds: int

    class _PlatformSettingsInstance(Protocol):
        profile: _EnvironmentProfileValue
        api: _APISettings
        gateway: _GatewaySettings
        executor: _ExecutorSettings
        runtime: _RuntimeSettings
        auth: _AuthSettings
        timeouts: _TimeoutSettings

    class _PlatformSettingsType(Protocol):
        def for_profile(
            self,
            profile: str | _EnvironmentProfileValue,
            *,
            overrides: Mapping[str, Mapping[str, object]] | None = None,
        ) -> _PlatformSettingsInstance: ...

        def from_env(
            self, environ: Mapping[str, str] | None = None
        ) -> _PlatformSettingsInstance: ...

    class _EnvironmentProfileType(Protocol):
        LOCAL: _EnvironmentProfileValue
        DEV: _EnvironmentProfileValue
        STAGING: _EnvironmentProfileValue
        PRODUCTION: _EnvironmentProfileValue

    class _EnvironmentProfileValue(Protocol):
        value: str

    EnvironmentProfile: _EnvironmentProfileType
    PlatformSettings: _PlatformSettingsType
else:
    from agentsty_platform.config import EnvironmentProfile, PlatformSettings


@pytest.mark.unit
def test_local_profile_secure_defaults() -> None:
    settings = PlatformSettings.for_profile(EnvironmentProfile.LOCAL)

    assert settings.profile == EnvironmentProfile.LOCAL
    assert settings.profile.value == EnvironmentProfile.LOCAL.value
    assert settings.gateway.internal_only is True
    assert settings.gateway.require_tls is False
    assert settings.executor.isolation_mode == "process"
    assert settings.runtime.expose_vendor_credentials is False
    assert settings.auth.required is False
    assert settings.auth.allow_anonymous_local is True


@pytest.mark.unit
def test_production_profile_uses_stronger_secure_defaults() -> None:
    settings = PlatformSettings.for_profile(EnvironmentProfile.PRODUCTION)

    assert settings.gateway.internal_only is True
    assert settings.gateway.require_tls is True
    assert settings.gateway.base_url.startswith("https://")
    assert settings.executor.backend == "kubernetes"
    assert settings.executor.isolation_mode == "virtual_machine"
    assert (
        settings.runtime.sandbox_image_reference
        == "ghcr.io/agentsty/agentsty-sandbox:prod"
    )
    assert settings.runtime.expose_vendor_credentials is False
    assert settings.auth.required is True
    assert settings.auth.mode == "jwt"
    assert settings.auth.allow_anonymous_local is False
    assert 1 <= settings.timeouts.request_timeout_seconds <= 600
    assert (
        settings.timeouts.request_timeout_seconds
        <= settings.timeouts.execution_timeout_seconds
        <= 3600
    )


@pytest.mark.unit
def test_from_env_applies_centralized_overrides() -> None:
    settings = PlatformSettings.from_env(
        {
            "AGENTSTY_PROFILE": "dev",
            "AGENTSTY_API_BIND_PORT": "9001",
            "AGENTSTY_RUNTIME_WORKSPACE_ROOT": "/srv/agentsty/runtime",
            "AGENTSTY_RUNTIME_SANDBOX_IMAGE": "registry.internal/agentsty/sandbox:dev-42",
            "AGENTSTY_TIMEOUT_REQUEST_SECONDS": "45",
            "AGENTSTY_AUTH_AUDIENCE": "internal-agents",
        }
    )

    assert settings.profile == EnvironmentProfile.DEV
    assert settings.profile.value == EnvironmentProfile.DEV.value
    assert settings.api.bind_port == 9001
    assert settings.runtime.workspace_root == Path("/srv/agentsty/runtime")
    assert (
        settings.runtime.sandbox_image_reference
        == "registry.internal/agentsty/sandbox:dev-42"
    )
    assert settings.timeouts.request_timeout_seconds == 45
    assert settings.auth.audience == "internal-agents"


@pytest.mark.unit
def test_from_env_uses_process_environment_when_no_mapping_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTSTY_PROFILE", "dev")
    monkeypatch.setenv("AGENTSTY_AUTH_AUDIENCE", "process-env-audience")

    settings = PlatformSettings.from_env()

    assert settings.profile == EnvironmentProfile.DEV
    assert settings.auth.required is True
    assert settings.auth.audience == "process-env-audience"


@pytest.mark.unit
def test_non_local_profiles_reject_process_isolation() -> None:
    with pytest.raises(ValueError, match="stronger isolation"):
        _ = PlatformSettings.for_profile(
            EnvironmentProfile.STAGING,
            overrides={"executor": {"isolation_mode": "process"}},
        )


@pytest.mark.unit
def test_gateway_internal_only_cannot_be_disabled() -> None:
    with pytest.raises(ValueError, match="internal_only"):
        _ = PlatformSettings.for_profile(
            EnvironmentProfile.LOCAL,
            overrides={"gateway": {"internal_only": False}},
        )


@pytest.mark.unit
def test_jwt_auth_requires_issuer_and_audience() -> None:
    with pytest.raises(ValueError, match="auth.issuer and auth.audience"):
        _ = PlatformSettings.for_profile(
            EnvironmentProfile.LOCAL,
            overrides={
                "auth": {
                    "mode": "jwt",
                    "required": True,
                    "issuer": None,
                    "audience": None,
                    "allow_anonymous_local": False,
                }
            },
        )

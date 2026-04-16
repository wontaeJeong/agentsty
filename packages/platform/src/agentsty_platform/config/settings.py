"""Structured typed settings for the shared platform boundary."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from typing import Protocol, TypedDict, cast

EnvParser = Callable[[str], object]
SectionOverrides = Mapping[str, object]
VALID_PROFILES = {"local", "dev", "staging", "production"}


class ProfileValue(Protocol):
    """Minimal runtime contract for exported environment profile values."""

    value: str


class ProfileFactory(Protocol):
    """Runtime constructor shape for the exported environment profile enum."""

    def __call__(self, value: str) -> ProfileValue: ...


class APIOverrides(TypedDict, total=False):
    bind_host: str
    bind_port: int
    base_path: str
    cors_allowed_origins: tuple[str, ...]
    trusted_proxy_cidrs: tuple[str, ...]


class GatewayOverrides(TypedDict, total=False):
    base_url: str
    internal_only: bool
    require_tls: bool
    audience: str
    request_path: str


class ExecutorOverrides(TypedDict, total=False):
    backend: str
    isolation_mode: str
    max_concurrency: int
    allow_privileged_containers: bool


class RuntimeOverrides(TypedDict, total=False):
    backend: str
    workspace_root: Path
    sandbox_image_reference: str | None
    allow_network_egress: bool
    expose_vendor_credentials: bool


class ObservabilityOverrides(TypedDict, total=False):
    service_name: str
    log_level: str
    metrics_enabled: bool
    traces_enabled: bool


class PersistenceOverrides(TypedDict, total=False):
    database_url: str
    artifact_root: Path
    artifact_ttl_hours: int
    redact_sensitive_artifacts: bool


class TimeoutOverrides(TypedDict, total=False):
    request_timeout_seconds: int
    execution_timeout_seconds: int
    cancellation_grace_period_seconds: int


class AuthOverrides(TypedDict, total=False):
    mode: str
    required: bool
    issuer: str | None
    audience: str | None
    allow_anonymous_local: bool


class KubernetesOverrides(TypedDict, total=False):
    api_server_url: str
    kubeconfig_path: Path | None
    kube_context: str | None


def _normalize_profile_name(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_PROFILES:
        msg = f"unsupported environment profile: {value!r}"
        raise ValueError(msg)
    return normalized


def _profile_name(value: str | ProfileValue) -> str:
    if isinstance(value, str):
        return value
    return value.value


def _runtime_environment_profile(value: str) -> ProfileValue:
    profile_type = cast(
        ProfileFactory,
        import_module("agentsty_platform.config.profiles").EnvironmentProfile,
    )
    return profile_type(value)


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    msg = f"invalid boolean value: {value!r}"
    raise ValueError(msg)


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_auth_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"none", "gateway_token", "jwt"}:
        msg = f"unsupported auth mode: {value!r}"
        raise ValueError(msg)
    return normalized


def _merge_overrides(
    settings: PlatformSettings, overrides: Mapping[str, SectionOverrides]
) -> PlatformSettings:
    updated = settings
    for section, section_overrides in overrides.items():
        section_data = cast(object, dict(section_overrides))
        if section == "api":
            updated = replace(
                updated,
                api=replace(updated.api, **cast(APIOverrides, section_data)),
            )
        elif section == "gateway":
            updated = replace(
                updated,
                gateway=replace(
                    updated.gateway, **cast(GatewayOverrides, section_data)
                ),
            )
        elif section == "executor":
            updated = replace(
                updated,
                executor=replace(
                    updated.executor, **cast(ExecutorOverrides, section_data)
                ),
            )
        elif section == "runtime":
            updated = replace(
                updated,
                runtime=replace(
                    updated.runtime, **cast(RuntimeOverrides, section_data)
                ),
            )
        elif section == "observability":
            updated = replace(
                updated,
                observability=replace(
                    updated.observability,
                    **cast(ObservabilityOverrides, section_data),
                ),
            )
        elif section == "persistence":
            updated = replace(
                updated,
                persistence=replace(
                    updated.persistence,
                    **cast(PersistenceOverrides, section_data),
                ),
            )
        elif section == "timeouts":
            updated = replace(
                updated,
                timeouts=replace(
                    updated.timeouts, **cast(TimeoutOverrides, section_data)
                ),
            )
        elif section == "auth":
            updated = replace(
                updated,
                auth=replace(updated.auth, **cast(AuthOverrides, section_data)),
            )
        elif section == "kubernetes":
            updated = replace(
                updated,
                kubernetes=replace(
                    updated.kubernetes,
                    **cast(KubernetesOverrides, section_data),
                ),
            )
        else:
            raise KeyError(f"unsupported settings section override: {section}")
    return updated


@dataclass(frozen=True, slots=True)
class APISettings:
    """North-south API settings."""

    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    base_path: str = "/v1"
    cors_allowed_origins: tuple[str, ...] = ()
    trusted_proxy_cidrs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.bind_host:
            raise ValueError("api.bind_host must not be empty")
        if not 1 <= self.bind_port <= 65_535:
            raise ValueError("api.bind_port must be between 1 and 65535")
        if not self.base_path.startswith("/"):
            raise ValueError("api.base_path must start with '/'")


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    """Internal LLM gateway access settings."""

    base_url: str = "http://127.0.0.1:9000"
    internal_only: bool = True
    require_tls: bool = False
    audience: str = "agentsty-gateway"
    request_path: str = "/v1/chat/completions"

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("gateway.base_url must not be empty")
        if not self.request_path.startswith("/"):
            raise ValueError("gateway.request_path must start with '/'")
        if self.require_tls and not self.base_url.startswith("https://"):
            raise ValueError("gateway.base_url must use https when TLS is required")
        if not self.internal_only:
            raise ValueError("gateway.internal_only must remain enabled")


@dataclass(frozen=True, slots=True)
class ExecutorSettings:
    """Sandbox executor configuration contract."""

    backend: str = "local"
    isolation_mode: str = "process"
    max_concurrency: int = 4
    allow_privileged_containers: bool = False

    def __post_init__(self) -> None:
        if not self.backend:
            raise ValueError("executor.backend must not be empty")
        if not self.isolation_mode:
            raise ValueError("executor.isolation_mode must not be empty")
        if self.max_concurrency < 1:
            raise ValueError("executor.max_concurrency must be at least 1")
        if self.allow_privileged_containers:
            raise ValueError(
                "executor.allow_privileged_containers must remain disabled"
            )


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Agent runtime adapter selection and safety settings."""

    backend: str = "opencode"
    workspace_root: Path = Path(".agentsty/runtime")
    sandbox_image_reference: str | None = None
    allow_network_egress: bool = False
    expose_vendor_credentials: bool = False

    def __post_init__(self) -> None:
        if not self.backend:
            raise ValueError("runtime.backend must not be empty")
        if self.sandbox_image_reference is not None:
            image_reference = self.sandbox_image_reference.strip()
            if not image_reference:
                raise ValueError("runtime.sandbox_image_reference must not be empty")
            object.__setattr__(self, "sandbox_image_reference", image_reference)
        if self.expose_vendor_credentials:
            raise ValueError(
                "runtime.expose_vendor_credentials must remain disabled for sandboxes"
            )


@dataclass(frozen=True, slots=True)
class KubernetesSettings:
    """Non-local Kubernetes control-plane access settings."""

    api_server_url: str = "https://kubernetes.default.svc.cluster.local"
    kubeconfig_path: Path | None = None
    kube_context: str | None = None
    shared_state_server: str | None = None
    shared_state_path: str | None = None

    def __post_init__(self) -> None:
        if not self.api_server_url.startswith("https://"):
            raise ValueError("kubernetes.api_server_url must use https")
        if self.kube_context is not None and not self.kube_context.strip():
            raise ValueError("kubernetes.kube_context must not be blank")
        if self.shared_state_server is not None:
            shared_state_server = self.shared_state_server.strip()
            if not shared_state_server:
                raise ValueError("kubernetes.shared_state_server must not be blank")
            object.__setattr__(self, "shared_state_server", shared_state_server)
        if self.shared_state_path is not None:
            shared_state_path = self.shared_state_path.strip()
            if not shared_state_path:
                raise ValueError("kubernetes.shared_state_path must not be blank")
            if not shared_state_path.startswith("/"):
                raise ValueError(
                    "kubernetes.shared_state_path must be an absolute path"
                )
            object.__setattr__(self, "shared_state_path", shared_state_path.rstrip("/"))
        if (self.shared_state_server is None) != (self.shared_state_path is None):
            raise ValueError(
                "kubernetes.shared_state_server and kubernetes.shared_state_path must be configured together"
            )


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Logging, metrics, and tracing defaults."""

    service_name: str = "agentsty-platform"
    log_level: str = "INFO"
    metrics_enabled: bool = True
    traces_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.service_name:
            raise ValueError("observability.service_name must not be empty")
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError("observability.log_level must be a standard logging level")


@dataclass(frozen=True, slots=True)
class PersistenceSettings:
    """Persistence and artifact retention settings."""

    database_url: str = "sqlite:///./agentsty.db"
    artifact_root: Path = Path(".agentsty/artifacts")
    artifact_ttl_hours: int = 24
    redact_sensitive_artifacts: bool = True

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("persistence.database_url must not be empty")
        if self.artifact_ttl_hours < 1:
            raise ValueError("persistence.artifact_ttl_hours must be at least 1")


@dataclass(frozen=True, slots=True)
class TimeoutSettings:
    """Bounded request and execution timeouts."""

    request_timeout_seconds: int = 60
    execution_timeout_seconds: int = 900
    cancellation_grace_period_seconds: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.request_timeout_seconds <= 600:
            raise ValueError(
                "timeouts.request_timeout_seconds must be between 1 and 600"
            )
        if not 5 <= self.execution_timeout_seconds <= 3_600:
            raise ValueError(
                "timeouts.execution_timeout_seconds must be between 5 and 3600"
            )
        if self.request_timeout_seconds > self.execution_timeout_seconds:
            raise ValueError(
                "timeouts.request_timeout_seconds must not exceed execution timeout"
            )
        if not 1 <= self.cancellation_grace_period_seconds <= 300:
            raise ValueError(
                "timeouts.cancellation_grace_period_seconds must be between 1 and 300"
            )


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Gateway and API authentication controls."""

    mode: str = "none"
    required: bool = False
    issuer: str | None = None
    audience: str | None = None
    allow_anonymous_local: bool = True

    def __post_init__(self) -> None:
        mode = _parse_auth_mode(self.mode)
        object.__setattr__(self, "mode", mode)
        if self.required and mode == "none":
            raise ValueError("auth.mode must not be 'none' when auth is required")
        if mode == "jwt" and (not self.issuer or not self.audience):
            raise ValueError("auth.issuer and auth.audience are required for jwt mode")


@dataclass(frozen=True, slots=True)
class PlatformSettings:
    """Aggregate application settings with profile-aware secure defaults."""

    profile: ProfileValue
    api: APISettings
    gateway: GatewaySettings
    executor: ExecutorSettings
    runtime: RuntimeSettings
    kubernetes: KubernetesSettings
    observability: ObservabilitySettings
    persistence: PersistenceSettings
    timeouts: TimeoutSettings
    auth: AuthSettings

    def __post_init__(self) -> None:
        if _profile_name(self.profile) == "local":
            if self.gateway.require_tls:
                raise ValueError(
                    "local profile must not require TLS for the internal gateway"
                )
            if not self.auth.allow_anonymous_local:
                raise ValueError(
                    "local profile must allow explicit anonymous local access"
                )
            return

        if self.executor.isolation_mode == "process":
            raise ValueError(
                "non-local profiles must use stronger isolation than local process execution"
            )
        if self.runtime.sandbox_image_reference is None:
            raise ValueError(
                "non-local profiles must define runtime.sandbox_image_reference"
            )
        if self.auth.allow_anonymous_local:
            raise ValueError(
                "non-local profiles must disable anonymous local auth bypass"
            )
        if not self.auth.required:
            raise ValueError("non-local profiles must require authentication")
        if not self.gateway.require_tls:
            raise ValueError("non-local profiles must require TLS for gateway access")
        if not self.gateway.base_url.startswith("https://"):
            raise ValueError("non-local profiles must use an https gateway URL")
        if self.kubernetes.shared_state_server is None:
            raise ValueError(
                "non-local profiles must configure kubernetes.shared_state_server"
            )
        if self.kubernetes.shared_state_path is None:
            raise ValueError(
                "non-local profiles must configure kubernetes.shared_state_path"
            )

    @classmethod
    def for_profile(
        cls,
        profile: str | ProfileValue,
        *,
        overrides: Mapping[str, SectionOverrides] | None = None,
    ) -> PlatformSettings:
        """Build settings for a profile with optional nested overrides."""

        settings = _profile_defaults(_normalize_profile_name(_profile_name(profile)))
        if overrides:
            settings = _merge_overrides(settings, overrides)
        return settings

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PlatformSettings:
        """Build settings from the centralized environment override contract."""

        env = dict(os.environ if environ is None else environ)
        profile = _normalize_profile_name(env.get("AGENTSTY_PROFILE", "local"))
        overrides: dict[str, dict[str, object]] = {}

        env_specs: tuple[tuple[str, str, str, EnvParser], ...] = (
            ("AGENTSTY_API_BIND_HOST", "api", "bind_host", str),
            ("AGENTSTY_API_BIND_PORT", "api", "bind_port", int),
            ("AGENTSTY_API_BASE_PATH", "api", "base_path", str),
            (
                "AGENTSTY_API_CORS_ALLOWED_ORIGINS",
                "api",
                "cors_allowed_origins",
                _parse_csv,
            ),
            (
                "AGENTSTY_API_TRUSTED_PROXY_CIDRS",
                "api",
                "trusted_proxy_cidrs",
                _parse_csv,
            ),
            ("AGENTSTY_GATEWAY_BASE_URL", "gateway", "base_url", str),
            ("AGENTSTY_GATEWAY_INTERNAL_ONLY", "gateway", "internal_only", _parse_bool),
            ("AGENTSTY_GATEWAY_REQUIRE_TLS", "gateway", "require_tls", _parse_bool),
            ("AGENTSTY_GATEWAY_AUDIENCE", "gateway", "audience", str),
            ("AGENTSTY_GATEWAY_REQUEST_PATH", "gateway", "request_path", str),
            ("AGENTSTY_EXECUTOR_BACKEND", "executor", "backend", str),
            ("AGENTSTY_EXECUTOR_ISOLATION_MODE", "executor", "isolation_mode", str),
            ("AGENTSTY_EXECUTOR_MAX_CONCURRENCY", "executor", "max_concurrency", int),
            (
                "AGENTSTY_EXECUTOR_ALLOW_PRIVILEGED_CONTAINERS",
                "executor",
                "allow_privileged_containers",
                _parse_bool,
            ),
            ("AGENTSTY_RUNTIME_BACKEND", "runtime", "backend", str),
            ("AGENTSTY_RUNTIME_WORKSPACE_ROOT", "runtime", "workspace_root", Path),
            (
                "AGENTSTY_RUNTIME_SANDBOX_IMAGE",
                "runtime",
                "sandbox_image_reference",
                str,
            ),
            (
                "AGENTSTY_RUNTIME_ALLOW_NETWORK_EGRESS",
                "runtime",
                "allow_network_egress",
                _parse_bool,
            ),
            (
                "AGENTSTY_RUNTIME_EXPOSE_VENDOR_CREDENTIALS",
                "runtime",
                "expose_vendor_credentials",
                _parse_bool,
            ),
            (
                "AGENTSTY_KUBERNETES_API_SERVER_URL",
                "kubernetes",
                "api_server_url",
                str,
            ),
            (
                "AGENTSTY_KUBERNETES_KUBECONFIG",
                "kubernetes",
                "kubeconfig_path",
                Path,
            ),
            (
                "AGENTSTY_KUBERNETES_CONTEXT",
                "kubernetes",
                "kube_context",
                str,
            ),
            (
                "AGENTSTY_KUBERNETES_SHARED_STATE_SERVER",
                "kubernetes",
                "shared_state_server",
                str,
            ),
            (
                "AGENTSTY_KUBERNETES_SHARED_STATE_PATH",
                "kubernetes",
                "shared_state_path",
                str,
            ),
            (
                "AGENTSTY_OBSERVABILITY_SERVICE_NAME",
                "observability",
                "service_name",
                str,
            ),
            ("AGENTSTY_OBSERVABILITY_LOG_LEVEL", "observability", "log_level", str),
            (
                "AGENTSTY_OBSERVABILITY_METRICS_ENABLED",
                "observability",
                "metrics_enabled",
                _parse_bool,
            ),
            (
                "AGENTSTY_OBSERVABILITY_TRACES_ENABLED",
                "observability",
                "traces_enabled",
                _parse_bool,
            ),
            ("AGENTSTY_PERSISTENCE_DATABASE_URL", "persistence", "database_url", str),
            (
                "AGENTSTY_PERSISTENCE_ARTIFACT_ROOT",
                "persistence",
                "artifact_root",
                Path,
            ),
            (
                "AGENTSTY_PERSISTENCE_ARTIFACT_TTL_HOURS",
                "persistence",
                "artifact_ttl_hours",
                int,
            ),
            (
                "AGENTSTY_PERSISTENCE_REDACT_SENSITIVE_ARTIFACTS",
                "persistence",
                "redact_sensitive_artifacts",
                _parse_bool,
            ),
            (
                "AGENTSTY_TIMEOUT_REQUEST_SECONDS",
                "timeouts",
                "request_timeout_seconds",
                int,
            ),
            (
                "AGENTSTY_TIMEOUT_EXECUTION_SECONDS",
                "timeouts",
                "execution_timeout_seconds",
                int,
            ),
            (
                "AGENTSTY_TIMEOUT_CANCELLATION_GRACE_SECONDS",
                "timeouts",
                "cancellation_grace_period_seconds",
                int,
            ),
            ("AGENTSTY_AUTH_MODE", "auth", "mode", _parse_auth_mode),
            ("AGENTSTY_AUTH_REQUIRED", "auth", "required", _parse_bool),
            ("AGENTSTY_AUTH_ISSUER", "auth", "issuer", str),
            ("AGENTSTY_AUTH_AUDIENCE", "auth", "audience", str),
            (
                "AGENTSTY_AUTH_ALLOW_ANONYMOUS_LOCAL",
                "auth",
                "allow_anonymous_local",
                _parse_bool,
            ),
        )

        for env_var, section, key, parser in env_specs:
            raw_value = env.get(env_var)
            if raw_value is None:
                continue
            overrides.setdefault(section, {})[key] = parser(raw_value)

        return cls.for_profile(profile, overrides=overrides)


def _profile_defaults(profile: str) -> PlatformSettings:
    runtime_profile = _runtime_environment_profile(profile)
    if profile == "local":
        return PlatformSettings(
            profile=runtime_profile,
            api=APISettings(),
            gateway=GatewaySettings(),
            executor=ExecutorSettings(),
            runtime=RuntimeSettings(),
            kubernetes=KubernetesSettings(),
            observability=ObservabilitySettings(log_level="DEBUG"),
            persistence=PersistenceSettings(),
            timeouts=TimeoutSettings(),
            auth=AuthSettings(),
        )

    base_url = f"https://gateway.{profile}.internal"
    tag = "prod" if profile == "production" else profile
    return PlatformSettings(
        profile=runtime_profile,
        api=APISettings(bind_host="0.0.0.0"),
        gateway=GatewaySettings(base_url=base_url, require_tls=True),
        executor=ExecutorSettings(
            backend="kubernetes", isolation_mode="virtual_machine"
        ),
        runtime=RuntimeSettings(
            workspace_root=Path(f"/var/lib/agentsty/{profile}/runtime"),
            sandbox_image_reference=(f"ghcr.io/agentsty/agentsty-sandbox:{tag}"),
        ),
        kubernetes=KubernetesSettings(
            shared_state_server=f"agentsty-state.{profile}.internal",
            shared_state_path=f"/exports/agentsty/{profile}",
        ),
        observability=ObservabilitySettings(),
        persistence=PersistenceSettings(
            database_url=(
                f"sqlite:////var/lib/agentsty/{profile}/runtime/"
                "_service_state/nonlocal-persistence.sqlite3"
            ),
            artifact_root=Path(f"/var/lib/agentsty/{profile}/artifacts"),
            artifact_ttl_hours=168,
        ),
        timeouts=TimeoutSettings(
            request_timeout_seconds=120, execution_timeout_seconds=1_200
        ),
        auth=AuthSettings(
            mode="jwt",
            required=True,
            issuer=f"https://auth.{profile}.internal",
            audience="agentsty-api",
            allow_anonymous_local=False,
        ),
    )

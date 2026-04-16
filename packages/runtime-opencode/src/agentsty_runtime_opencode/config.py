"""Managed OpenCode config and environment injection helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PROVIDER_ID = "internal-openai"
MANAGED_PERMISSION_CONFIG: dict[str, str] = {
    "question": "allow",
    "plan_enter": "allow",
    "plan_exit": "allow",
}
MANAGED_PERMISSION_RULESET: tuple[dict[str, str], ...] = (
    {"permission": "question", "pattern": "*", "action": "allow"},
    {"permission": "plan_enter", "pattern": "*", "action": "allow"},
    {"permission": "plan_exit", "pattern": "*", "action": "allow"},
)
OPENCODE_DISABLED_ENV: dict[str, str] = {
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    "OPENCODE_DISABLE_AUTOCOMPACT": "1",
}


@dataclass(frozen=True, slots=True)
class OpenCodeGatewayConfig:
    tenant_id: str
    provider_id: str
    model_id: str
    gateway_base_url: str
    authorization_header: str | None

    @property
    def model_label(self) -> str:
        return f"{self.provider_id}/{self.model_id}"


def build_managed_env(
    gateway: OpenCodeGatewayConfig,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(OPENCODE_DISABLED_ENV)
    env["OPENCODE_PERMISSION"] = json.dumps(
        list(MANAGED_PERMISSION_RULESET),
        separators=(",", ":"),
    )
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        build_managed_config(gateway),
        separators=(",", ":"),
    )
    if extra_env:
        env.update(extra_env)
    return env


def build_managed_config(gateway: OpenCodeGatewayConfig) -> dict[str, object]:
    provider_headers = {"X-Agentsty-Tenant": gateway.tenant_id}
    if gateway.authorization_header is not None:
        provider_headers["Authorization"] = gateway.authorization_header

    return {
        "autoupdate": False,
        "share": "disabled",
        "permission": dict(MANAGED_PERMISSION_CONFIG),
        "plugin": [],
        "formatter": False,
        "lsp": False,
        "enabled_providers": [gateway.provider_id],
        "model": gateway.model_label,
        "small_model": gateway.model_label,
        "provider": {
            gateway.provider_id: {
                "api": "openai",
                "id": gateway.provider_id,
                "name": "Agentsty Internal Gateway",
                "options": {
                    "baseURL": gateway.gateway_base_url,
                    "apiKey": _api_key_from_header(gateway.authorization_header),
                    "timeout": 30000,
                },
                "models": {
                    gateway.model_id: {
                        "id": gateway.model_id,
                        "name": gateway.model_id,
                        "headers": provider_headers,
                    }
                },
            }
        },
    }


def provider_id_for_target(provider: str | None) -> str:
    if provider is None:
        return DEFAULT_PROVIDER_ID
    cleaned = provider.strip()
    return cleaned or DEFAULT_PROVIDER_ID


def gateway_provider_base_url(base_url: str, request_path: str) -> str:
    path = request_path.strip()
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
            break
    else:
        if "/" in path:
            path = path.rsplit("/", maxsplit=1)[0] or "/"

    split = urlsplit(base_url)
    prefix = split.path.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    merged = f"{prefix}{suffix}".rstrip("/")
    return urlunsplit((split.scheme, split.netloc, merged, split.query, split.fragment))


def prompt_from_messages(messages: tuple[tuple[str, str], ...]) -> str:
    rendered = [f"{role}: {content}" for role, content in messages if content.strip()]
    if not rendered:
        raise ValueError("OpenCode prompt must include at least one non-empty message")
    return "\n\n".join(rendered)


def _api_key_from_header(authorization_header: str | None) -> str:
    if authorization_header is None:
        return "anonymous-local"
    prefix = "Bearer "
    if authorization_header.startswith(prefix):
        token = authorization_header[len(prefix) :].strip()
        if token:
            return token
    return authorization_header.strip() or "managed-internal-token"

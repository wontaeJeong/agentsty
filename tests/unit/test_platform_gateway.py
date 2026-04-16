from __future__ import annotations

import importlib
from typing import Any

import pytest


def _gateway_module() -> Any:
    return importlib.import_module("agentsty_platform.gateway")


def _config_module() -> Any:
    return importlib.import_module("agentsty_platform.config")


def _domain_module() -> Any:
    return importlib.import_module("agentsty_platform.domain")


@pytest.mark.unit
def test_internal_gateway_client_shapes_requests_and_issues_internal_auth() -> None:
    gateway = _gateway_module()
    config = _config_module()
    domain = _domain_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    transport = gateway.LocalGatewayTransport()
    token_provider = gateway.StaticInternalAuthTokenProvider(ttl_seconds=120)
    client = gateway.InternalGatewayClient(
        settings=settings,
        transport=transport,
        token_provider=token_provider,
    )
    tenant = domain.TenantId("tenant-a")
    trace_context = importlib.import_module(
        "agentsty_platform.observability"
    ).TraceContext.new(
        tenant_id=tenant,
    )
    request = gateway.GatewayRequest(
        tenant_id=tenant,
        target=gateway.GatewayModelTarget(
            provider="internal-openai", model="gpt-4o-mini"
        ),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.SYSTEM,
                content="Be concise.",
            ),
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="Hello gateway",
            ),
        ),
        trace_context=trace_context,
        allowlist=gateway.GatewayAllowlist(
            allowed_providers=("internal-openai",),
            allowed_models=("gpt-4o-mini",),
        ),
    )

    response = client.generate(request)

    assert response.message.role is gateway.GatewayMessageRole.ASSISTANT
    assert response.message.content.startswith("local gateway echo: Hello gateway")
    captured_call = transport.captured_calls[-1]
    assert captured_call.endpoint.url == "http://127.0.0.1:9000/v1/chat/completions"
    assert captured_call.request.target.label == "internal-openai/gpt-4o-mini"
    assert captured_call.auth_context.authorization_header is not None
    assert captured_call.auth_context.token.audience == settings.gateway.audience
    assert captured_call.auth_context.trace_context == trace_context


@pytest.mark.unit
def test_gateway_request_allowlist_enforces_provider_and_model_policy() -> None:
    gateway = _gateway_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    with pytest.raises(domain.PolicyViolationError, match="not allowed"):
        _ = gateway.GatewayRequest(
            tenant_id=tenant,
            target=gateway.GatewayModelTarget(
                provider="internal-anthropic", model="claude-3"
            ),
            messages=(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.USER,
                    content="hello",
                ),
            ),
            allowlist=gateway.GatewayAllowlist(
                allowed_providers=("internal-openai",),
                allowed_models=("gpt-4o-mini",),
            ),
        )


@pytest.mark.unit
def test_internal_auth_required_profiles_reject_missing_token_provider() -> None:
    gateway = _gateway_module()
    config = _config_module()
    domain = _domain_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.PRODUCTION)
    client = gateway.InternalGatewayClient(
        settings=settings,
        transport=gateway.LocalGatewayTransport(),
    )
    request = gateway.GatewayRequest(
        tenant_id=domain.TenantId("tenant-a"),
        target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="hello",
            ),
        ),
    )

    with pytest.raises(domain.AuthenticationError, match="requires a token provider"):
        _ = client.generate(request)


@pytest.mark.unit
def test_internal_gateway_client_retries_retryable_failures_and_returns_response() -> (
    None
):
    gateway = _gateway_module()
    config = _config_module()
    domain = _domain_module()

    tenant = domain.TenantId("tenant-a")
    recovery_response = gateway.GatewayResponse(
        tenant_id=tenant,
        target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
        message=gateway.GatewayMessage(
            role=gateway.GatewayMessageRole.ASSISTANT,
            content="Recovered after retry",
        ),
    )
    transport = gateway.LocalGatewayTransport(
        scripted_outcomes=[
            gateway.GatewayFailure(
                gateway.GatewayFailureKind.UNAVAILABLE,
                "gateway unavailable",
            ),
            recovery_response,
        ]
    )
    client = gateway.InternalGatewayClient(
        settings=config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL),
        transport=transport,
        token_provider=gateway.StaticInternalAuthTokenProvider(),
        max_attempts=2,
    )
    request = gateway.GatewayRequest(
        tenant_id=tenant,
        target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="hello",
            ),
        ),
    )

    response = client.generate(request)

    assert response.message.content == "Recovered after retry"
    assert len(transport.captured_calls) == 2


@pytest.mark.unit
def test_gateway_failure_mapping_uses_shared_domain_taxonomy() -> None:
    gateway = _gateway_module()
    domain = _domain_module()

    auth_error = gateway.map_gateway_failure(
        gateway.gateway_failure_from_status(401, "missing token")
    )
    quota_error = gateway.map_gateway_failure(
        gateway.gateway_failure_from_status(429, "rate limited")
    )
    timeout_error = gateway.map_gateway_failure(
        gateway.GatewayFailure(
            gateway.GatewayFailureKind.TIMEOUT,
            "gateway timed out",
        )
    )

    assert isinstance(auth_error, domain.AuthenticationError)
    assert isinstance(quota_error, domain.QuotaExceededError)
    assert isinstance(timeout_error, domain.TimeoutError)
    assert quota_error.details.retryable is True
    assert timeout_error.details.category is domain.ErrorCategory.TIMEOUT


@pytest.mark.unit
def test_gateway_public_exports_support_local_smoke_path() -> None:
    gateway = _gateway_module()
    config = _config_module()
    domain = _domain_module()

    settings = config.PlatformSettings.for_profile(config.EnvironmentProfile.LOCAL)
    endpoint = gateway.GatewayEndpoint.from_settings(settings)
    client = gateway.InternalGatewayClient(
        settings=settings,
        transport=gateway.LocalGatewayTransport(),
        token_provider=gateway.StaticInternalAuthTokenProvider(),
    )
    request = gateway.GatewayRequest(
        tenant_id=domain.TenantId("tenant-a"),
        target=gateway.GatewayModelTarget(model="gpt-4o-mini"),
        messages=(
            gateway.GatewayMessage(
                role=gateway.GatewayMessageRole.USER,
                content="smoke test",
            ),
        ),
    )

    response = client.generate(request)

    assert endpoint.internal_only is True
    assert endpoint.url.endswith("/v1/chat/completions")
    assert response.usage.total_tokens >= 2

"""Gateway boundary for internal model access through a shared abstraction."""

from __future__ import annotations

from importlib import import_module
from typing import cast

CapturedGatewayCall: object
GatewayAllowlist: object
GatewayClient: object
GatewayEndpoint: object
GatewayFailure: object
GatewayFailureKind: object
GatewayFinishReason: object
GatewayMessage: object
GatewayMessageRole: object
GatewayModelTarget: object
GatewayRequest: object
GatewayResponse: object
GatewaySampling: object
GatewayTransport: object
GatewayUsage: object
HTTPGatewayTransport: object
InternalAuthContext: object
InternalAuthToken: object
InternalAuthTokenProvider: object
InternalGatewayClient: object
LocalGatewayTransport: object
ServiceGatewayTokenProvider: object
StaticInternalAuthTokenProvider: object
gateway_failure_from_status: object
map_gateway_failure: object
resolve_internal_auth_context: object

_CONTRACT_EXPORTS = {
    "GatewayAllowlist",
    "GatewayFinishReason",
    "GatewayMessage",
    "GatewayMessageRole",
    "GatewayModelTarget",
    "GatewayRequest",
    "GatewayResponse",
    "GatewaySampling",
    "GatewayUsage",
}
_AUTH_EXPORTS = {
    "InternalAuthContext",
    "InternalAuthToken",
    "InternalAuthTokenProvider",
    "StaticInternalAuthTokenProvider",
    "resolve_internal_auth_context",
}
_ERROR_EXPORTS = {
    "GatewayFailure",
    "GatewayFailureKind",
    "gateway_failure_from_status",
    "map_gateway_failure",
}
_CLIENT_EXPORTS = {
    "GatewayClient",
    "GatewayEndpoint",
    "GatewayTransport",
    "InternalGatewayClient",
}
_LOCAL_EXPORTS = {
    "CapturedGatewayCall",
    "LocalGatewayTransport",
}
_NON_LOCAL_EXPORTS = {
    "HTTPGatewayTransport",
    "ServiceGatewayTokenProvider",
}

__all__ = [
    "CapturedGatewayCall",
    "GatewayAllowlist",
    "GatewayClient",
    "GatewayEndpoint",
    "GatewayFailure",
    "GatewayFailureKind",
    "GatewayFinishReason",
    "GatewayMessage",
    "GatewayMessageRole",
    "GatewayModelTarget",
    "GatewayRequest",
    "GatewayResponse",
    "GatewaySampling",
    "GatewayTransport",
    "GatewayUsage",
    "HTTPGatewayTransport",
    "InternalAuthContext",
    "InternalAuthToken",
    "InternalAuthTokenProvider",
    "InternalGatewayClient",
    "LocalGatewayTransport",
    "ServiceGatewayTokenProvider",
    "StaticInternalAuthTokenProvider",
    "gateway_failure_from_status",
    "map_gateway_failure",
    "resolve_internal_auth_context",
]


def __getattr__(name: str) -> object:
    """Lazily expose gateway symbols without eager package-local imports."""

    if name in _CONTRACT_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.contracts"), name),
        )
    if name in _AUTH_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.auth"), name),
        )
    if name in _ERROR_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.errors"), name),
        )
    if name == "GatewayClient":
        return cast(
            object, import_module("agentsty_platform.gateway.client").GatewayClient
        )
    if name in _CLIENT_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.client"), name),
        )
    if name in _LOCAL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.local"), name),
        )
    if name in _NON_LOCAL_EXPORTS:
        return cast(
            object,
            getattr(import_module("agentsty_platform.gateway.nonlocal"), name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

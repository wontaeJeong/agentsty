"""API-layer authentication, principal resolution, and tenant binding."""

# pyright: reportMissingImports=false

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import import_module
from typing import Protocol, cast


class RequestLike(Protocol):
    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def state(self) -> object: ...


class _JWKLike(Protocol):
    key: object


class _PyJWKClientLike(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> _JWKLike: ...


class _PyJWKClientFactory(Protocol):
    def __call__(self, uri: str) -> _PyJWKClientLike: ...


class _JWTDecoder(Protocol):
    def __call__(
        self,
        token: str,
        key: object,
        *,
        algorithms: list[str],
        audience: str,
        issuer: str,
        options: Mapping[str, object],
    ) -> Mapping[str, object]: ...


class _DomainErrorFactory(Protocol):
    def __call__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> Exception: ...


class _TenantIdFactory(Protocol):
    def __call__(self, value: str) -> object: ...


def _empty_claims() -> dict[str, object]:
    return {}


def _empty_jwks_clients() -> dict[str, _PyJWKClientLike]:
    return {}


_JWT_MODULE = import_module("jwt")
_INVALID_TOKEN_ERROR = cast(type[Exception], _JWT_MODULE.InvalidTokenError)
_PY_JWK_CLIENT = cast(_PyJWKClientFactory, _JWT_MODULE.PyJWKClient)
_JWT_DECODE = cast(_JWTDecoder, _JWT_MODULE.decode)


class AuthSettingsLike(Protocol):
    mode: str
    required: bool
    issuer: str | None
    audience: str | None
    allow_anonymous_local: bool


class SettingsLike(Protocol):
    profile: object
    auth: object


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Verified principal identity plus authorized tenant scope."""

    subject: str
    issuer: str
    audience: str
    authorized_tenant_ids: tuple[str, ...]
    token_id: str | None = None
    claims: Mapping[str, object] = field(default_factory=_empty_claims)

    def __post_init__(self) -> None:
        subject = self.subject.strip()
        issuer = self.issuer.strip()
        audience = self.audience.strip()
        if not subject:
            raise ValueError("principal subject must not be empty")
        if not issuer:
            raise ValueError("principal issuer must not be empty")
        if not audience:
            raise ValueError("principal audience must not be empty")
        tenants = tuple(
            dict.fromkeys(tenant.strip() for tenant in self.authorized_tenant_ids)
        )
        if any(not tenant for tenant in tenants):
            raise ValueError("authorized tenant ids must not contain empty values")
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "audience", audience)
        object.__setattr__(self, "authorized_tenant_ids", tenants)


class PrincipalVerifier(Protocol):
    """Verifier for bearer tokens on non-local API requests."""

    def verify_bearer_token(
        self,
        token: str,
        *,
        settings: SettingsLike,
    ) -> AuthenticatedPrincipal: ...


@dataclass(slots=True)
class JWTPrincipalVerifier:
    """Generic JWT/OIDC verifier backed by the configured issuer JWKS."""

    _jwks_clients: dict[str, _PyJWKClientLike] = field(
        default_factory=_empty_jwks_clients
    )

    def verify_bearer_token(
        self,
        token: str,
        *,
        settings: SettingsLike,
    ) -> AuthenticatedPrincipal:
        auth = cast(AuthSettingsLike, settings.auth)
        issuer = (auth.issuer or "").strip()
        audience = (auth.audience or "").strip()
        if auth.mode != "jwt":
            raise _authentication_error(
                "API authentication requires jwt mode for bearer token verification",
                metadata=(("auth_mode", auth.mode),),
            )
        if not issuer or not audience:
            raise _authentication_error(
                "API authentication settings must define issuer and audience",
                metadata=(("auth_mode", auth.mode),),
            )
        try:
            signing_key = self._jwks_client(issuer).get_signing_key_from_jwt(token)
            claims = _JWT_DECODE(
                token,
                signing_key.key,
                algorithms=[
                    "RS256",
                    "RS384",
                    "RS512",
                    "ES256",
                    "ES384",
                    "ES512",
                    "EdDSA",
                ],
                audience=audience,
                issuer=issuer,
                options={
                    "require": ["sub", "iss", "aud", "exp"],
                    "verify_signature": True,
                },
            )
        except _INVALID_TOKEN_ERROR as error:
            raise _authentication_error(
                "bearer token verification failed",
                metadata=(("reason", error.__class__.__name__),),
            ) from error
        return principal_from_claims(claims, issuer=issuer, audience=audience)

    def _jwks_client(self, issuer: str) -> _PyJWKClientLike:
        client = self._jwks_clients.get(issuer)
        if client is None:
            client = _PY_JWK_CLIENT(f"{issuer.rstrip('/')}/.well-known/jwks.json")
            self._jwks_clients[issuer] = client
        return client


@dataclass(frozen=True, slots=True)
class EffectiveRequestIdentity:
    """Resolved request identity and tenant after authn/authz checks."""

    tenant_id: object
    principal_subject: str | None
    auth_mode: str
    authorized_tenant_ids: tuple[str, ...] = ()


def resolve_submission_identity(
    *,
    request: RequestLike,
    settings: SettingsLike,
    verifier: PrincipalVerifier | None,
    requested_tenant_id: str,
) -> EffectiveRequestIdentity:
    return _resolve_effective_identity(
        request=request,
        settings=settings,
        verifier=verifier,
        requested_tenant_id=requested_tenant_id,
        metadata_transport="fastapi",
    )


def resolve_job_identity(
    *,
    request: RequestLike,
    settings: SettingsLike,
    verifier: PrincipalVerifier | None,
    requested_tenant_id: str | None,
) -> EffectiveRequestIdentity:
    return _resolve_effective_identity(
        request=request,
        settings=settings,
        verifier=verifier,
        requested_tenant_id=requested_tenant_id,
        metadata_transport="fastapi.job",
    )


def principal_from_claims(
    claims: Mapping[str, object],
    *,
    issuer: str,
    audience: str,
) -> AuthenticatedPrincipal:
    subject = _required_string_claim(claims, "sub")
    authorized_tenant_ids = _tenant_ids_from_claims(claims)
    if not authorized_tenant_ids:
        raise _authorization_error(
            "authenticated principal is not bound to any tenant",
            metadata=(("subject", subject),),
        )
    token_id = _optional_string_claim(claims, "jti")
    return AuthenticatedPrincipal(
        subject=subject,
        issuer=issuer,
        audience=audience,
        authorized_tenant_ids=authorized_tenant_ids,
        token_id=token_id,
        claims=dict(claims),
    )


def _resolve_effective_identity(
    *,
    request: RequestLike,
    settings: SettingsLike,
    verifier: PrincipalVerifier | None,
    requested_tenant_id: str | None,
    metadata_transport: str,
) -> EffectiveRequestIdentity:
    if _allow_anonymous_local(settings) and _authorization_header(request) is None:
        if requested_tenant_id is None or not requested_tenant_id.strip():
            raise _invalid_request_error(
                "tenant selection is required when using anonymous local access",
                metadata=(("transport", metadata_transport),),
            )
        return EffectiveRequestIdentity(
            tenant_id=_tenant_id(requested_tenant_id),
            principal_subject=None,
            auth_mode="anonymous_local",
        )

    principal = _resolve_authenticated_principal(
        request=request,
        settings=settings,
        verifier=verifier,
    )
    effective_tenant_id = _bind_tenant_to_principal(
        principal=principal,
        requested_tenant_id=requested_tenant_id,
    )
    return EffectiveRequestIdentity(
        tenant_id=_tenant_id(effective_tenant_id),
        principal_subject=principal.subject,
        auth_mode="authenticated_principal",
        authorized_tenant_ids=principal.authorized_tenant_ids,
    )


def _resolve_authenticated_principal(
    *,
    request: RequestLike,
    settings: SettingsLike,
    verifier: PrincipalVerifier | None,
) -> AuthenticatedPrincipal:
    state_principal = cast(
        object | None, getattr(request.state, "agentsty_principal", None)
    )
    if state_principal is not None:
        return _principal_from_state(state_principal, settings=settings)
    authorization_header = _authorization_header(request)
    auth = cast(AuthSettingsLike, settings.auth)
    if authorization_header is None:
        raise _authentication_error(
            "bearer authentication is required for this profile",
            metadata=(("auth_mode", auth.mode),),
        )
    if verifier is None:
        raise _authentication_error(
            "no principal verifier is configured for bearer authentication",
            metadata=(("auth_mode", auth.mode),),
        )
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _authentication_error(
            "authorization header must use bearer token authentication",
            metadata=(("authorization_scheme", scheme or "missing"),),
        )
    return verifier.verify_bearer_token(token.strip(), settings=settings)


def _principal_from_state(
    principal: object,
    *,
    settings: SettingsLike,
) -> AuthenticatedPrincipal:
    claims = cast(Mapping[str, object], getattr(principal, "claims", principal))
    auth = cast(AuthSettingsLike, settings.auth)
    issuer = _optional_string_claim(claims, "iss") or (auth.issuer or "")
    audience = _optional_string_claim(claims, "aud") or (auth.audience or "")
    return principal_from_claims(claims, issuer=issuer, audience=audience)


def _bind_tenant_to_principal(
    *,
    principal: AuthenticatedPrincipal,
    requested_tenant_id: str | None,
) -> str:
    if not principal.authorized_tenant_ids:
        raise _authorization_error(
            "authenticated principal is not bound to any tenant",
            metadata=(("subject", principal.subject),),
        )
    if requested_tenant_id is None or not requested_tenant_id.strip():
        if len(principal.authorized_tenant_ids) == 1:
            return principal.authorized_tenant_ids[0]
        raise _invalid_request_error(
            "tenant selection is required for principals authorized for multiple tenants",
            metadata=(("subject", principal.subject),),
        )
    if requested_tenant_id not in principal.authorized_tenant_ids:
        raise _authorization_error(
            "requested tenant is not authorized for the authenticated principal",
            metadata=(
                ("subject", principal.subject),
                ("requested_tenant_id", requested_tenant_id),
            ),
        )
    return requested_tenant_id


def _tenant_ids_from_claims(claims: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for claim_name in ("tenant_id", "tenant", "tid"):
        value = _optional_string_claim(claims, claim_name)
        if value is not None:
            values.append(value)
    for claim_name in ("tenant_ids", "tenants"):
        raw_value = claims.get(claim_name)
        if isinstance(raw_value, str):
            values.extend(_split_tenant_string(raw_value))
            continue
        if isinstance(raw_value, (list, tuple)):
            sequence = cast(list[object] | tuple[object, ...], raw_value)
            values.extend(
                item.strip()
                for item in sequence
                if isinstance(item, str) and item.strip()
            )
    return tuple(dict.fromkeys(values))


def _split_tenant_string(value: str) -> tuple[str, ...]:
    return tuple(
        token.strip()
        for chunk in value.split(",")
        for token in chunk.split()
        if token.strip()
    )


def _required_string_claim(claims: Mapping[str, object], name: str) -> str:
    value = _optional_string_claim(claims, name)
    if value is None:
        raise _authentication_error(
            f"bearer token is missing required '{name}' claim",
            metadata=(("claim", name),),
        )
    return value


def _optional_string_claim(claims: Mapping[str, object], name: str) -> str | None:
    value = claims.get(name)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        sequence = cast(list[object], value)
        if len(sequence) == 1 and isinstance(sequence[0], str):
            stripped = sequence[0].strip()
            return stripped or None
    if isinstance(value, tuple):
        tuple_sequence = cast(tuple[object, ...], value)
        if len(tuple_sequence) == 1 and isinstance(tuple_sequence[0], str):
            stripped = tuple_sequence[0].strip()
            return stripped or None
    return None


def _authorization_header(request: RequestLike) -> str | None:
    value = request.headers.get("authorization")
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _allow_anonymous_local(settings: SettingsLike) -> bool:
    profile_value = getattr(settings.profile, "value", settings.profile)
    auth = cast(AuthSettingsLike, settings.auth)
    return (
        cast(str, profile_value) == "local"
        and not auth.required
        and auth.allow_anonymous_local
    )


def _tenant_id(value: str) -> object:
    domain = import_module("agentsty_platform.domain")
    return cast(_TenantIdFactory, domain.TenantId)(value)


def _authentication_error(
    message: str,
    *,
    metadata: tuple[tuple[str, str], ...] = (),
) -> Exception:
    domain = import_module("agentsty_platform.domain")
    return cast(_DomainErrorFactory, domain.AuthenticationError)(
        message, metadata=metadata
    )


def _authorization_error(
    message: str,
    *,
    metadata: tuple[tuple[str, str], ...] = (),
) -> Exception:
    domain = import_module("agentsty_platform.domain")
    return cast(_DomainErrorFactory, domain.AuthorizationError)(
        message, metadata=metadata
    )


def _invalid_request_error(
    message: str,
    *,
    metadata: tuple[tuple[str, str], ...] = (),
) -> Exception:
    domain = import_module("agentsty_platform.domain")
    return cast(_DomainErrorFactory, domain.InvalidRequestError)(
        message, metadata=metadata
    )

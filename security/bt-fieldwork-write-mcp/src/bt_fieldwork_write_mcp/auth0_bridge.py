"""Optional Auth0 OIDC proxy. Off unless FW_WRITE_AUTH_MODE=auth0_bridge.

Uses FastMCP's Auth0Provider. This module does not contact Auth0 until
build_auth0_provider() runs, and that call is refused until every production
requirement below is present. Direct JWT mode does not import this provider.
"""

from __future__ import annotations

import hmac
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from .config import Settings

_WILDCARD = ("*", "?", "[")
_MCP_PATH = "/mcp"


def bridge_requested(settings: Settings) -> bool:
    return settings.auth_mode == "auth0_bridge"


def parse_subject_map(pairs: tuple[str, ...]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            continue
        sub, email = item.split("=", 1)
        sub = sub.strip()
        email = email.strip().lower()
        if sub and email:
            mapped[sub] = email
    return mapped


def resolve_human_identity(
    upstream: dict[str, Any] | None,
    *,
    permitted: tuple[str, ...],
    subject_map: dict[str, str],
) -> dict[str, str] | None:
    """Stable subject plus verified email, or a configured subject map.

    preferred_username and an unverified email are ignored. The chosen email
    must be in the permitted list. A map that disagrees with a verified email
    is rejected.
    """
    claims = dict(upstream or {})
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return None
    email = str(claims.get("email") or "").strip().lower()
    verified = claims.get("email_verified") is True
    mapped = subject_map.get(sub, "")
    if verified and email and mapped and email != mapped:
        return None
    if verified and email:
        chosen = email
    elif mapped:
        chosen = mapped
    else:
        return None
    allowed = {item.strip().lower() for item in permitted if item.strip()}
    if chosen not in allowed:
        return None
    return {"sub": sub, "email": chosen}


def _https(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.fragment


def published_resource(base_url: str) -> str:
    return base_url.rstrip("/") + _MCP_PATH


def _exact_https_callback(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path:
        return False
    if parsed.username or parsed.password or parsed.fragment:
        return False
    if any(mark in value for mark in _WILDCARD):
        return False
    return True


def _temp_roots() -> set[Path]:
    roots = {Path("/tmp"), Path("/var/tmp"), Path("/private/tmp"), Path(tempfile.gettempdir())}
    resolved: set[Path] = set()
    for root in roots:
        resolved.add(root)
        try:
            resolved.add(root.resolve())
        except OSError:
            continue
    return resolved


def storage_path_ok(path_str: str) -> bool:
    if not path_str:
        return False
    raw = Path(path_str)
    if not raw.is_absolute():
        return False
    try:
        canonical = raw.resolve(strict=False)
    except OSError:
        return False
    for root in _temp_roots():
        if canonical == root or root in canonical.parents:
            return False
    return True


def fernet_key_ok(value: str) -> bool:
    try:
        Fernet(value.encode("utf-8"))
    except Exception:
        return False
    return True


def _same(left: str, right: str) -> bool:
    return bool(left) and bool(right) and hmac.compare_digest(left, right)


def bridge_blockers(settings: Settings) -> list[str]:
    """Reasons the optional bridge must not start. Empty means local config is complete.

    Fernet and storage are checked here, before any Fieldwork secret is loaded.
    Comparison with a loaded Fieldwork key happens later in build_auth0_provider.
    """
    if not bridge_requested(settings):
        return []
    blocked: list[str] = []
    if not _https(settings.auth0_config_url):
        blocked.append("auth0_config_url")
    if not settings.auth0_client_id:
        blocked.append("auth0_client_id")
    if not settings.auth0_client_secret:
        blocked.append("auth0_client_secret")
    if not _https(settings.auth0_base_url):
        blocked.append("auth0_base_url")
    expected = published_resource(settings.auth0_base_url) if _https(settings.auth0_base_url) else ""
    resource = settings.oauth_resource.rstrip("/")
    audience = settings.oauth_audience.rstrip("/")
    auth0_audience = settings.auth0_audience.rstrip("/")
    if not expected or resource != expected or audience != expected or auth0_audience != expected:
        blocked.append("auth0_resource")
    if not settings.auth0_allowed_callbacks or not all(_exact_https_callback(item) for item in settings.auth0_allowed_callbacks):
        blocked.append("auth0_allowed_callbacks")
    if len(settings.auth0_jwt_signing_key) < 32:
        blocked.append("auth0_jwt_signing_key")
    if not fernet_key_ok(settings.auth0_storage_key):
        blocked.append("auth0_storage_key")
    if not storage_path_ok(settings.auth0_storage_path):
        blocked.append("auth0_storage_path")
    if _same(settings.auth0_jwt_signing_key, settings.auth0_storage_key) or _same(settings.auth0_client_secret, settings.auth0_jwt_signing_key) or _same(settings.auth0_client_secret, settings.auth0_storage_key):
        blocked.append("auth0_keys_not_distinct")
    if not settings.permitted_users:
        blocked.append("permitted_users")
    return blocked


def fieldwork_key_reused(settings: Settings, fieldwork_key: str) -> bool:
    """True when the loaded Fieldwork key matches any OAuth secret. Values are not returned."""
    return any(
        _same(fieldwork_key, candidate)
        for candidate in (settings.auth0_client_secret, settings.auth0_jwt_signing_key, settings.auth0_storage_key)
    )


def encrypted_store(settings: Settings) -> Any:
    from key_value.aio.stores.filetree import FileTreeStore
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

    if not storage_path_ok(settings.auth0_storage_path) or not fernet_key_ok(settings.auth0_storage_key):
        raise ValueError("auth0_storage_path")
    path = Path(settings.auth0_storage_path).resolve(strict=False)
    path.mkdir(parents=True, exist_ok=True)
    return FernetEncryptionWrapper(
        key_value=FileTreeStore(data_directory=path),
        fernet=Fernet(settings.auth0_storage_key.encode("utf-8")),
    )


def _claim_subset(verified: dict[str, Any]) -> dict[str, Any] | None:
    sub = str(verified.get("sub") or "").strip()
    if not sub:
        return None
    email = str(verified.get("email") or "").strip().lower()
    return {"sub": sub, "email": email, "email_verified": verified.get("email_verified") is True}


def build_auth0_provider(settings: Settings, fieldwork_key: str = "") -> Any:
    """Construct Auth0Provider. Performs OIDC discovery. Callers must want the bridge."""
    blockers = bridge_blockers(settings)
    if blockers:
        raise ValueError("auth0_bridge_blocked:" + ",".join(blockers))
    if fieldwork_key_reused(settings, fieldwork_key):
        raise ValueError("auth0_bridge_blocked:fieldwork_key_reused_as_oauth_secret")
    from fastmcp.server.auth.providers.auth0 import Auth0Provider
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    class _BtAuth0(Auth0Provider):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._refresh_without_new_id_token = False

        async def exchange_refresh_token(self, client: Any, refresh_token: Any, scopes: list[str]) -> Any:
            previous = self._refresh_without_new_id_token
            self._refresh_without_new_id_token = True
            try:
                return await super().exchange_refresh_token(client, refresh_token, scopes)
            finally:
                self._refresh_without_new_id_token = previous

        async def _extract_upstream_claims(self, idp_tokens: dict[str, Any]) -> dict[str, Any] | None:
            id_token = idp_tokens.get("id_token") if isinstance(idp_tokens, dict) else None
            if not isinstance(id_token, str) or not id_token:
                return None
            verifier = getattr(self, "_token_validator", None)
            jwks_uri = getattr(verifier, "jwks_uri", None)
            if not jwks_uri:
                return None
            id_verifier = JWTVerifier(
                jwks_uri=str(jwks_uri),
                issuer=str(getattr(verifier, "issuer", "") or ""),
                audience=settings.auth0_client_id,
            )
            checked = await id_verifier.verify_token(id_token)
            if checked is None:
                if not self._refresh_without_new_id_token:
                    return None
                # Auth0 may omit a new ID token on refresh. Do not keep trusting an
                # expired ID token. The access-token subject plus the configured
                # subject map remains the identity for that refreshed session.
                return None
            claims = _claim_subset(dict(checked.claims or {}))
            access_token = idp_tokens.get("access_token")
            if isinstance(access_token, str) and access_token:
                access = await verifier.verify_token(access_token)
                access_sub = str(getattr(access, "subject", "") or "") if access is not None else ""
                if claims and access_sub and claims["sub"] != access_sub:
                    return {"sub": access_sub, "email": "", "email_verified": False}
            return claims

    provider = _BtAuth0(
        config_url=settings.auth0_config_url,
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        audience=settings.auth0_audience,
            base_url=settings.auth0_base_url,
            resource_base_url=settings.auth0_base_url,
            required_scopes=["openid", "email"],
        allowed_client_redirect_uris=list(settings.auth0_allowed_callbacks),
        client_storage=encrypted_store(settings),
        jwt_signing_key=settings.auth0_jwt_signing_key,
        require_authorization_consent=True,
    )
    if getattr(provider, "_forward_pkce", None) is not True:
        raise ValueError("auth0_bridge_blocked:pkce")
    if getattr(provider, "_require_authorization_consent", None) is not True:
        raise ValueError("auth0_bridge_blocked:consent")
    return provider


def bridge_identity_from_token(token: Any, settings: Settings) -> dict[str, str] | None:
    """Identity for a tool call. Never returns the bearer token."""
    if token is None:
        return None
    raw = dict(getattr(token, "claims", None) or {})
    upstream = raw.get("upstream_claims") if isinstance(raw.get("upstream_claims"), dict) else {}
    access_sub = str(getattr(token, "subject", None) or raw.get("sub") or "").strip()
    id_sub = str(upstream.get("sub") or "").strip()
    if access_sub and id_sub and access_sub != id_sub:
        return None
    claims = {
        "sub": access_sub or id_sub,
        "email": upstream.get("email"),
        "email_verified": upstream.get("email_verified"),
    }
    return resolve_human_identity(
        claims,
        permitted=settings.permitted_users,
        subject_map=parse_subject_map(settings.auth0_subject_map),
    )

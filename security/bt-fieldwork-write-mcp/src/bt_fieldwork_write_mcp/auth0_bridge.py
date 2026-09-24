"""Optional Auth0 OIDC proxy. Off unless FW_WRITE_AUTH_MODE=auth0_bridge.

Uses FastMCP's Auth0Provider. This module does not contact Auth0 until
build_auth0_provider() runs, and that call is refused until every production
requirement below is present. Direct JWT mode does not import this provider.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import Settings

_WILDCARD = ("*", "?", "[")


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
    return parsed.scheme == "https" and bool(parsed.netloc)


def _exact_callback(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return False
    if any(mark in value for mark in _WILDCARD):
        return False
    return True


def bridge_blockers(settings: Settings) -> list[str]:
    """Reasons the optional bridge must not start. Empty means the config is complete."""
    if not bridge_requested(settings):
        return []
    blocked: list[str] = []
    if not _https(settings.auth0_config_url):
        blocked.append("auth0_config_url")
    if not settings.auth0_client_id:
        blocked.append("auth0_client_id")
    if not settings.auth0_client_secret:
        blocked.append("auth0_client_secret")
    if not settings.auth0_audience or settings.auth0_audience != settings.oauth_audience:
        blocked.append("auth0_audience")
    if not _https(settings.auth0_base_url):
        blocked.append("auth0_base_url")
    if not settings.auth0_allowed_callbacks or not all(_exact_callback(item) for item in settings.auth0_allowed_callbacks):
        blocked.append("auth0_allowed_callbacks")
    if len(settings.auth0_jwt_signing_key) < 32:
        blocked.append("auth0_jwt_signing_key")
    if not settings.auth0_storage_key:
        blocked.append("auth0_storage_key")
    path = settings.auth0_storage_path
    if not path or path.startswith("/tmp") or path == "/tmp":
        blocked.append("auth0_storage_path")
    fieldwork_key = os.environ.get("FIELDWORK_API_KEY", "")
    if fieldwork_key and (
        fieldwork_key == settings.auth0_client_secret
        or fieldwork_key == settings.auth0_jwt_signing_key
        or fieldwork_key == settings.auth0_storage_key
    ):
        blocked.append("fieldwork_key_reused_as_oauth_secret")
    if not settings.permitted_users:
        blocked.append("permitted_users")
    return blocked


def encrypted_store(settings: Settings) -> Any:
    from cryptography.fernet import Fernet
    from key_value.aio.stores.filetree import FileTreeStore
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

    path = Path(settings.auth0_storage_path)
    if not path.is_absolute() or str(path).startswith("/tmp"):
        raise ValueError("auth0_storage_path")
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


def build_auth0_provider(settings: Settings) -> Any:
    """Construct Auth0Provider. Performs OIDC discovery. Callers must want the bridge."""
    blockers = bridge_blockers(settings)
    if blockers:
        raise ValueError("auth0_bridge_blocked:" + ",".join(blockers))
    from fastmcp.server.auth.providers.auth0 import Auth0Provider
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    class _BtAuth0(Auth0Provider):
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
                return None
            return _claim_subset(dict(checked.claims or {}))

    provider = _BtAuth0(
        config_url=settings.auth0_config_url,
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        audience=settings.auth0_audience,
        base_url=settings.auth0_base_url,
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
    claims = {key: upstream.get(key) for key in ("sub", "email", "email_verified")}
    if not claims.get("sub"):
        claims["sub"] = getattr(token, "subject", None)
    return resolve_human_identity(
        claims,
        permitted=settings.permitted_users,
        subject_map=parse_subject_map(settings.auth0_subject_map),
    )

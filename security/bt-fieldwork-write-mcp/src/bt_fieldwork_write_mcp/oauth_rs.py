"""OAuth 2.1 resource-server token checks. This process does not issue tokens."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.request import urlopen

import jwt
from jwt import PyJWKClient

from .config import Settings

try:
    from mcp.server.auth.provider import AccessToken
except ImportError:  # pragma: no cover - SDK required for the HTTP server
    AccessToken = None  # type: ignore[misc,assignment]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scopes(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("scope") or claims.get("scopes") or []
    if isinstance(raw, str):
        return [item for item in raw.replace(",", " ").split() if item]
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return []


def _audience_ok(claims: dict[str, Any], audience: str) -> bool:
    aud = claims.get("aud")
    if isinstance(aud, list):
        return audience in [str(item) for item in aud]
    return str(aud or "") == audience


def _email(claims: dict[str, Any]) -> str:
    return str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()


class JwtTokenVerifier:
    """Verify issuer, audience, expiry, scopes, and a permitted user.

    Authorization-server setup remains a deployment gate. Missing issuer/JWKS
    or an empty permit list fails closed.
    """

    def __init__(self, settings: Settings, *, jwk_client: PyJWKClient | None = None) -> None:
        self.settings = settings
        self._jwk_client = jwk_client
        if settings.oauth_jwks_url and jwk_client is None:
            self._jwk_client = PyJWKClient(settings.oauth_jwks_url)

    def decode_claims(self, token: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        settings = self.settings
        if not settings.oauth_ready():
            return None
        options = {"require": ["exp", "iss", "aud"]}
        try:
            if self._jwk_client is not None:
                signing = self._jwk_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing.key,
                    algorithms=["RS256"],
                    issuer=settings.oauth_issuer,
                    audience=settings.oauth_audience,
                    options=options,
                    leeway=5,
                )
            elif settings.hs256_secret:
                claims = jwt.decode(
                    token,
                    settings.hs256_secret,
                    algorithms=["HS256"],
                    issuer=settings.oauth_issuer,
                    audience=settings.oauth_audience,
                    options=options,
                    leeway=5,
                )
            else:
                return None
        except jwt.PyJWTError:
            return None
        clock = now or _now()
        exp = claims.get("exp")
        if exp is None:
            return None
        try:
            if datetime.fromtimestamp(int(exp), tz=timezone.utc) <= clock:
                return None
        except (TypeError, ValueError, OSError):
            return None
        if str(claims.get("iss") or "") != settings.oauth_issuer:
            return None
        if not _audience_ok(claims, settings.oauth_audience):
            return None
        have = set(_scopes(claims))
        if not set(settings.required_scopes).issubset(have):
            return None
        email = _email(claims)
        if not settings.permitted_users or email not in settings.permitted_users:
            return None
        claims["_email"] = email
        return claims

    def verify(self, token: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        return self.decode_claims(token, now=now)

    async def verify_token(self, token: str) -> Any:
        claims = self.decode_claims(token)
        if claims is None or AccessToken is None:
            return None
        return AccessToken(
            token="[redacted]",
            client_id=str(claims.get("client_id") or claims.get("azp") or claims.get("sub") or ""),
            scopes=_scopes(claims),
            expires_at=int(claims["exp"]),
            resource=self.settings.oauth_resource,
            subject=str(claims.get("sub") or ""),
            claims={"iss": claims.get("iss"), "email": claims.get("_email"), "aud": claims.get("aud")},
        )


def identity_from_claims(claims: dict[str, Any]) -> dict[str, str]:
    return {
        "sub": str(claims.get("sub") or ""),
        "email": str(claims.get("_email") or _email(claims)),
    }


def fetch_jwks(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=15) as response:  # noqa: S310 - caller supplies configured HTTPS JWKS
        import json

        return json.loads(response.read().decode("utf-8"))

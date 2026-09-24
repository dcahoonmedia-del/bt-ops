"""OAuth resource-server rejection. No homemade bearer-key auth."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from bt_fieldwork_write_mcp.config import Settings
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier


def _settings(**overrides: object) -> Settings:
    values = dict(
        writes_enabled=False,
        mapping_verified=False,
        store_path=Path(tempfile.gettempdir()) / "unused.sqlite",
        api_base="https://api3.fieldworkhq.com/v3.1",
        oauth_issuer="https://issuer.example.test",
        oauth_audience="bt-fieldwork-write",
        oauth_resource="https://write.example.test/mcp",
        oauth_jwks_url="",
        hs256_secret="hs256-test-secret-32bytes-min-ok",
        required_scopes=("fieldwork.write",),
        permitted_users=("daniel@btpestcontrol.com",),
        operator_key="operator-test-key",
        proposal_ttl_seconds=1800,
        approval_ttl_seconds=900,
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


NOW = datetime.now(timezone.utc)


def _token(claims: dict | None = None, secret: str = "hs256-test-secret-32bytes-min-ok") -> str:
    payload = {
        "iss": "https://issuer.example.test",
        "aud": "bt-fieldwork-write",
        "sub": "user-1",
        "email": "daniel@btpestcontrol.com",
        "scope": "fieldwork.write",
        "exp": int((NOW + timedelta(minutes=10)).timestamp()),
        "iat": int(NOW.timestamp()),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


class OAuthRejectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = JwtTokenVerifier(_settings())

    def test_valid_permitted_user(self) -> None:
        claims = self.verifier.verify(_token(), now=NOW)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["_email"], "daniel@btpestcontrol.com")

    def test_rejected_wrong_issuer(self) -> None:
        self.assertIsNone(self.verifier.verify(_token({"iss": "https://evil.example"}), now=NOW))

    def test_rejected_wrong_audience(self) -> None:
        self.assertIsNone(self.verifier.verify(_token({"aud": "someone-else"}), now=NOW))

    def test_rejected_expired(self) -> None:
        token = _token({"exp": int((NOW - timedelta(minutes=1)).timestamp())})
        self.assertIsNone(self.verifier.verify(token, now=NOW))

    def test_rejected_missing_scope(self) -> None:
        self.assertIsNone(self.verifier.verify(_token({"scope": "openid"}), now=NOW))

    def test_rejected_unpermitted_user(self) -> None:
        self.assertIsNone(self.verifier.verify(_token({"email": "other@example.com"}), now=NOW))

    def test_rejected_when_oauth_not_configured(self) -> None:
        verifier = JwtTokenVerifier(_settings(oauth_issuer="", hs256_secret=""))
        self.assertFalse(verifier.settings.oauth_ready())
        self.assertIsNone(verifier.verify(_token(), now=NOW))

    def test_rejected_wrong_signature(self) -> None:
        self.assertIsNone(self.verifier.verify(_token(secret="wrong-secret-32bytes-minimum-ok!"), now=NOW))

    def test_verify_token_redacts_bearer(self) -> None:
        access = asyncio.run(self.verifier.verify_token(_token()))
        self.assertIsNotNone(access)
        self.assertEqual(access.token, "[redacted]")
        self.assertEqual(access.resource, "https://write.example.test/mcp")

    def test_verify_token_rejects_bad_bearer(self) -> None:
        access = asyncio.run(self.verifier.verify_token("not-a-jwt"))
        self.assertIsNone(access)

    def test_homemade_static_key_is_not_accepted_as_oauth(self) -> None:
        self.assertIsNone(self.verifier.verify("static-shared-connector-key", now=NOW))

"""Offline Auth0 bridge guards. These tests do not call Auth0 or ChatGPT."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from bt_fieldwork_write_mcp.auth0_bridge import (
    bridge_blockers,
    bridge_identity_from_token,
    build_auth0_provider,
    encrypted_store,
    resolve_human_identity,
)
from bt_fieldwork_write_mcp.config import Settings
from tests.test_write_mcp import _settings

PERMITTED = ("daniel@btpestcontrol.com",)
SIGNING = "bridge-signing-key-32-characters-min"


def _bridge(root: Path, **overrides: object) -> Settings:
    storage = Fernet.generate_key().decode("utf-8")
    values = dict(
        auth_mode="auth0_bridge",
        oauth_issuer="https://tenant.example.test/",
        oauth_audience="https://write.example.test/mcp",
        oauth_resource="https://write.example.test/mcp",
        permitted_users=PERMITTED,
        auth0_config_url="https://tenant.example.test/.well-known/openid-configuration",
        auth0_client_id="bridge-client",
        auth0_client_secret="bridge-client-secret-not-fieldwork",
        auth0_audience="https://write.example.test/mcp",
        auth0_base_url="https://write.example.test",
        auth0_allowed_callbacks=("https://chatgpt.com/connector/oauth/callback",),
        auth0_jwt_signing_key=SIGNING,
        auth0_storage_key=storage,
        auth0_storage_path=str(root),
        auth0_subject_map=("auth0|daniel=daniel@btpestcontrol.com",),
    )
    values.update(overrides)
    return _settings(root / "unused.sqlite", **values)


class _Token:
    def __init__(self, claims: dict, subject: str | None = None) -> None:
        self.claims = claims
        self.subject = subject


class Auth0BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".bridge-store-test"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_absent_by_default(self) -> None:
        settings = Settings.from_env()
        self.assertEqual(settings.auth_mode, "jwt")
        self.assertEqual(bridge_blockers(settings), [])
        self.assertFalse(settings.auth0_client_secret)

    def test_production_requirements_fail_closed(self) -> None:
        settings = _bridge(self.root, auth0_base_url="http://write.example.test")
        self.assertIn("auth0_base_url", bridge_blockers(settings))
        http_callback = _bridge(self.root, auth0_allowed_callbacks=("http://example.com/callback",))
        self.assertIn("auth0_allowed_callbacks", bridge_blockers(http_callback))
        userinfo = _bridge(self.root, auth0_allowed_callbacks=("https://user:secret@chatgpt.com/callback",))
        self.assertIn("auth0_allowed_callbacks", bridge_blockers(userinfo))
        fragment = _bridge(self.root, auth0_allowed_callbacks=("https://chatgpt.com/callback#frag",))
        self.assertIn("auth0_allowed_callbacks", bridge_blockers(fragment))
        wild = _bridge(self.root, auth0_allowed_callbacks=("https://*.example.com/cb",))
        self.assertIn("auth0_allowed_callbacks", bridge_blockers(wild))
        tmp = _bridge(self.root, auth0_storage_path="/tmp/bridge")
        self.assertIn("auth0_storage_path", bridge_blockers(tmp))
        private_tmp = _bridge(self.root, auth0_storage_path="/private/tmp/auth0-store")
        self.assertIn("auth0_storage_path", bridge_blockers(private_tmp))
        short = _bridge(self.root, auth0_jwt_signing_key="short-key")
        self.assertIn("auth0_jwt_signing_key", bridge_blockers(short))
        other_resource = _bridge(self.root, oauth_resource="https://different.example/mcp")
        self.assertIn("auth0_resource", bridge_blockers(other_resource))
        other_audience = _bridge(
            self.root,
            oauth_audience="https://different.example/mcp",
            auth0_audience="https://different.example/mcp",
        )
        self.assertIn("auth0_resource", bridge_blockers(other_audience))
        same = _bridge(self.root, auth0_jwt_signing_key=Fernet.generate_key().decode("utf-8"))
        # signing key may still be long enough; force it equal to the storage key
        tied = _bridge(self.root, auth0_jwt_signing_key=same.auth0_storage_key, auth0_storage_key=same.auth0_storage_key)
        self.assertIn("auth0_keys_not_distinct", bridge_blockers(tied))

    def test_identity_rules(self) -> None:
        mapped = {"auth0|daniel": "daniel@btpestcontrol.com"}
        ok = resolve_human_identity(
            {"sub": "auth0|daniel", "email": "daniel@btpestcontrol.com", "email_verified": True, "preferred_username": "nope"},
            permitted=PERMITTED,
            subject_map=mapped,
        )
        self.assertEqual(ok, {"sub": "auth0|daniel", "email": "daniel@btpestcontrol.com"})
        self.assertIsNone(resolve_human_identity({"sub": "auth0|daniel", "email": "daniel@btpestcontrol.com", "email_verified": False, "preferred_username": "daniel@btpestcontrol.com"}, permitted=PERMITTED, subject_map={}))
        self.assertIsNone(resolve_human_identity({"sub": "auth0|other", "email": "other@example.com", "email_verified": True}, permitted=PERMITTED, subject_map={}))
        self.assertIsNone(resolve_human_identity({"preferred_username": "daniel@btpestcontrol.com"}, permitted=PERMITTED, subject_map=mapped))
        mapped_only = resolve_human_identity({"sub": "auth0|daniel"}, permitted=PERMITTED, subject_map=mapped)
        self.assertEqual(mapped_only["email"], "daniel@btpestcontrol.com")
        conflict = resolve_human_identity(
            {"sub": "auth0|daniel", "email": "other@example.com", "email_verified": True},
            permitted=PERMITTED,
            subject_map=mapped,
        )
        self.assertIsNone(conflict)

    def test_token_identity_ignores_unverified_email_and_bearer(self) -> None:
        settings = _bridge(self.root)
        token = _Token(
            {"email": "daniel@btpestcontrol.com", "email_verified": True, "access_token": "upstream-secret", "upstream_claims": {"sub": "auth0|daniel"}},
            subject="auth0|daniel",
        )
        identity = bridge_identity_from_token(token, settings)
        self.assertEqual(identity["sub"], "auth0|daniel")
        self.assertNotIn("upstream-secret", str(identity))
        self.assertIsNone(bridge_identity_from_token(_Token({"email": "daniel@btpestcontrol.com", "email_verified": False}, subject="auth0|other"), settings))
        forged = bridge_identity_from_token(
            _Token(
                {"sub": "auth0|daniel", "upstream_claims": {"sub": "auth0|forged", "email": "daniel@btpestcontrol.com", "email_verified": True}},
                subject="auth0|daniel",
            ),
            settings,
        )
        self.assertIsNone(forged)
        from bt_fieldwork_write_mcp.auth0_bridge import fieldwork_key_reused

        self.assertTrue(fieldwork_key_reused(settings, settings.auth0_client_secret))
        self.assertFalse(fieldwork_key_reused(settings, "different-fieldwork-key"))
        self.assertNotIn(settings.auth0_client_secret, "fieldwork_key_reused_as_oauth_secret")

    def test_encrypted_store_survives_restart(self) -> None:
        import asyncio

        settings = _bridge(self.root)

        async def roundtrip() -> None:
            first = encrypted_store(settings)
            await first.put("one", {"redirect": "https://chatgpt.com/connector/oauth/callback"}, collection="clients")
            second = encrypted_store(settings)
            loaded = await second.get("one", collection="clients")
            self.assertEqual(loaded["redirect"], "https://chatgpt.com/connector/oauth/callback")

        asyncio.run(roundtrip())

    def test_provider_locks_consent_pkce_and_callbacks(self) -> None:
        from fastmcp.server.auth.oidc_proxy import OIDCConfiguration, OIDCProxy

        def fake_config(cls, config_url, strict, timeout_seconds):  # noqa: ANN001
            return OIDCConfiguration(
                issuer="https://tenant.example.test/",
                authorization_endpoint="https://tenant.example.test/authorize",
                token_endpoint="https://tenant.example.test/oauth/token",
                jwks_uri="https://tenant.example.test/.well-known/jwks.json",
                response_types_supported=["code"],
                subject_types_supported=["public"],
                id_token_signing_alg_values_supported=["RS256"],
            )

        original = OIDCProxy.get_oidc_configuration
        OIDCProxy.get_oidc_configuration = classmethod(fake_config)
        try:
            provider = build_auth0_provider(_bridge(self.root))
        finally:
            OIDCProxy.get_oidc_configuration = original
        self.assertIs(provider._require_authorization_consent, True)
        self.assertIs(provider._forward_pkce, True)
        self.assertEqual(provider._allowed_client_redirect_uris, ["https://chatgpt.com/connector/oauth/callback"])
        self.assertEqual(str(provider._token_validator.audience), "https://write.example.test/mcp")
        self.assertNotIn("bridge-client-secret", repr(provider))
        self.assertIn("offline_access", str(provider._extra_authorize_params.get("scope") or "").split())
        self.assertNotIn("offline_access", list(provider.required_scopes or []))

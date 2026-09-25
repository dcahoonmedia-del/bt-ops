"""Offline ASGI coverage for the real Auth0 bridge server.

Synthetic RSA tokens and a local JWKS stand in for Auth0. Nothing here is a
live Auth0 or ChatGPT login.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

import fastmcp.server.auth.oauth_proxy.proxy as proxy_mod
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration, OIDCProxy

from bt_fieldwork_write_mcp.server import build_bridge_server
from tests.test_auth0_bridge import _bridge
from tests.test_write_mcp import Harness

CALLBACK = "https://chatgpt.com/connector/oauth/callback"
RESOURCE = "https://write.example.test/mcp"
ISSUER = "https://tenant.example.test/"


class _Jwks(BaseHTTPRequestHandler):
    jwks = {"keys": []}

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(self.jwks).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _Upstream:
    access_token = ""
    id_token = ""
    refresh_calls = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.client_secret = "x"

    async def __aenter__(self) -> "_Upstream":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def fetch_token(self, url: str | None = None, **params: object) -> dict:
        return {
            "access_token": type(self).access_token,
            "id_token": type(self).id_token,
            "refresh_token": "up-refresh",
            "expires_in": 600,
            "token_type": "Bearer",
            "scope": "openid email",
        }

    async def refresh_token(self, url: str | None = None, **params: object) -> dict:
        type(self).refresh_calls += 1
        # Auth0 often omits a new ID token. The expired original must not be
        # required for a mapped subject to keep using the refreshed access token.
        return {
            "access_token": type(self).access_token,
            "expires_in": 600,
            "token_type": "Bearer",
            "scope": "openid email",
        }

    async def aclose(self) -> None:
        return None


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _pkce(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class BridgeAsgiTests(unittest.TestCase):
    def setUp(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        numbers = key.public_key().public_numbers()
        _Jwks.jwks = {"keys": [{"kty": "RSA", "kid": "test", "use": "sig", "alg": "RS256", "n": _b64(numbers.n), "e": _b64(numbers.e)}]}
        self.httpd = HTTPServer(("127.0.0.1", 0), _Jwks)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.jwks_url = f"http://127.0.0.1:{self.httpd.server_port}/jwks"
        self.original_oidc = OIDCProxy.get_oidc_configuration
        self.original_client = proxy_mod.AsyncOAuth2Client
        OIDCProxy.get_oidc_configuration = classmethod(self._discovery)
        proxy_mod.AsyncOAuth2Client = _Upstream
        self.h = Harness()
        self.root = Path(__file__).resolve().parents[1] / ".bridge-store-test"
        _Upstream.refresh_calls = 0
        self._set_identity("auth0|daniel", "daniel@btpestcontrol.com", True)

    def tearDown(self) -> None:
        OIDCProxy.get_oidc_configuration = self.original_oidc
        proxy_mod.AsyncOAuth2Client = self.original_client
        self.httpd.shutdown()
        self.httpd.server_close()
        self.h.close()

    def _discovery(self, cls, config_url, strict, timeout_seconds):  # noqa: ANN001
        return OIDCConfiguration(
            issuer=ISSUER,
            authorization_endpoint="https://tenant.example.test/authorize",
            token_endpoint="https://tenant.example.test/oauth/token",
            jwks_uri=self.jwks_url,
            response_types_supported=["code"],
            subject_types_supported=["public"],
            id_token_signing_alg_values_supported=["RS256"],
        )

    def _sign(self, claims: dict) -> str:
        return jwt.encode(claims, self.private, algorithm="RS256", headers={"kid": "test"})

    def _set_identity(self, sub: str, email: str, verified: bool, *, access_overrides: dict | None = None, id_overrides: dict | None = None) -> None:
        now = int(time.time())
        access = {"iss": ISSUER, "aud": RESOURCE, "sub": sub, "exp": now + 600, "iat": now, "scope": "openid email"}
        access.update(access_overrides or {})
        ident = {"iss": ISSUER, "aud": "bridge-client", "sub": sub, "email": email, "email_verified": verified, "exp": now + 600, "iat": now}
        ident.update(id_overrides or {})
        _Upstream.access_token = self._sign(access)
        _Upstream.id_token = self._sign(ident)

    def _app(self):
        settings = _bridge(self.root)
        mcp = build_bridge_server(settings, self.h.service, fieldwork_key="fieldwork-not-oauth")
        return mcp.http_app(transport="http", allowed_hosts=["*"])

    def _login(self, client: TestClient, verifier: str = "bridge-verifier-value-32b-minimum") -> tuple[str, str]:
        registered = client.post("/register", json={"redirect_uris": [CALLBACK], "client_name": "offline"})
        self.assertEqual(registered.status_code, 201, registered.text)
        client_id = registered.json()["client_id"]
        challenge = _pkce(verifier)
        started = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "st",
                "resource": RESOURCE,
            },
            follow_redirects=False,
        )
        consent = client.get(started.headers["location"].replace("https://write.example.test", ""))
        txn = re.search(r'name="txn_id" value="([^"]+)"', consent.text).group(1)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', consent.text).group(1)
        approved = client.post("/consent", data={"txn_id": txn, "csrf_token": csrf, "submit": "true", "action": "approve"}, follow_redirects=False)
        state = parse_qs(urlparse(approved.headers["location"]).query)["state"][0]
        callback = client.get("/auth/callback", params={"code": "idp-code", "state": state}, follow_redirects=False)
        query = parse_qs(urlparse(callback.headers["location"]).query)
        token = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": CALLBACK,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": RESOURCE,
            },
        )
        self.assertEqual(token.status_code, 200, token.text[:400])
        body = token.json()
        self.assertNotIn("up-refresh", body["access_token"])
        self.assertIn("refresh_token", body)
        return client_id, body["access_token"], body["refresh_token"], query["code"][0]

    def _call(self, client: TestClient, access: str, name: str, arguments: dict | None = None) -> str:
        headers = {"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        opened = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.assertEqual(opened.status_code, 200, opened.text[:300])
        session = opened.headers.get("mcp-session-id")
        if session:
            headers["mcp-session-id"] = session
        client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        called = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})
        self.assertEqual(called.status_code, 200, called.text[:400])
        return called.text

    def test_metadata_and_protocol_rejections(self) -> None:
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            meta = client.get("/.well-known/oauth-protected-resource/mcp")
            self.assertEqual(meta.status_code, 200)
            self.assertEqual(meta.json()["resource"], RESOURCE)
            registered = client.post("/register", json={"redirect_uris": [CALLBACK], "client_name": "offline"})
            client_id = registered.json()["client_id"]
            missing = client.get(
                "/authorize",
                params={"response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK, "state": "st"},
                follow_redirects=False,
            )
            self.assertIn("code_challenge", missing.headers.get("location", ""))
            wrong = client.get(
                "/authorize",
                params={"response_type": "code", "client_id": client_id, "redirect_uri": "https://evil.example/cb", "code_challenge": _pkce("x" * 43), "code_challenge_method": "S256", "state": "st"},
                follow_redirects=False,
            )
            self.assertEqual(wrong.status_code, 400)
            self.assertIn("Redirect URI", wrong.text)
            bad_pkce = client.get(
                "/authorize",
                params={"response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK, "code_challenge": _pkce("x" * 43), "code_challenge_method": "plain", "state": "st"},
                follow_redirects=False,
            )
            self.assertIn("code_challenge_method", bad_pkce.headers.get("location", "") + bad_pkce.text)
            denied = client.post("/mcp", headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
            self.assertEqual(denied.status_code, 401)

    def test_permitted_identity_reaches_handlers_and_writes_stay_off(self) -> None:
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            _client_id, access, _refresh, _code = self._login(client)
            report = self._call(client, access, "report_gates")
            self.assertIn('"ok":true', report.replace(" ", ""))
            self.assertIn('"writes_enabled":false', report.replace(" ", ""))
            self.assertIn('"live_auth0_login_observed_by_this_process":true', report.replace(" ", ""))
            proposed = self._call(client, access, "propose_write", {"operation": "update_service_location_notes", "payload": {"customer_id": 41, "location_id": 77, "notes": "standing note"}})
            self.assertIn("proposal_id", proposed)
            self.assertNotIn('"ok":false', proposed.replace(" ", "")[:80])
            self.assertFalse(any(call["method"] == "PATCH" for call in self.h.transport.calls))

    def test_disallowed_identity_cannot_operate(self) -> None:
        self._set_identity("auth0|other", "other@example.com", True)
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            _client_id, access, _refresh, _code = self._login(client, verifier="c" * 43)
            report = self._call(client, access, "report_gates")
            self.assertIn("oauth_rejected", report)
            self.assertNotIn("proposal_id", report)

    def test_bad_upstream_tokens_are_rejected(self) -> None:
        now = int(time.time())
        cases = [
            {"iss": "https://evil.example/"},
            {"aud": "https://other.example/mcp"},
            {"exp": now - 60},
        ]
        for override in cases:
            with self.subTest(override=override):
                self._set_identity("auth0|daniel", "daniel@btpestcontrol.com", True, access_overrides=override)
                with TestClient(self._app(), base_url="https://write.example.test") as client:
                    _client_id, access, _refresh, _code = self._login(client, verifier="d" * 43)
                    headers = {"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                    opened = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
                    self.assertEqual(opened.status_code, 401, opened.text[:300])
        self._set_identity("auth0|daniel", "daniel@btpestcontrol.com", True)
        _Upstream.access_token = _Upstream.access_token + "tamper"
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            _client_id, access, _refresh, _code = self._login(client, verifier="e" * 43)
            headers = {"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
            opened = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
            self.assertEqual(opened.status_code, 401)

    def test_forged_id_token_subject_does_not_override(self) -> None:
        now = int(time.time())
        access = self._sign({"iss": ISSUER, "aud": RESOURCE, "sub": "auth0|other", "exp": now + 600, "iat": now, "scope": "openid email"})
        ident = self._sign({"iss": ISSUER, "aud": "bridge-client", "sub": "auth0|daniel", "email": "daniel@btpestcontrol.com", "email_verified": True, "exp": now + 600, "iat": now})
        _Upstream.access_token = access
        _Upstream.id_token = ident
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            _client_id, token, _refresh, _code = self._login(client, verifier="f" * 43)
            report = self._call(client, token, "report_gates")
            self.assertIn("oauth_rejected", report)

    def test_refresh_without_new_id_token_keeps_mapped_session(self) -> None:
        now = int(time.time())
        _Upstream.id_token = self._sign({"iss": ISSUER, "aud": "bridge-client", "sub": "auth0|daniel", "email": "daniel@btpestcontrol.com", "email_verified": True, "exp": now - 30, "iat": now - 90})
        with TestClient(self._app(), base_url="https://write.example.test") as client:
            client_id, _access, refresh, code = self._login(client, verifier="g" * 43)
            replay = client.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK, "client_id": client_id, "code_verifier": "g" * 43, "resource": RESOURCE})
            self.assertNotEqual(replay.status_code, 200)
            other = client.post("/register", json={"redirect_uris": [CALLBACK], "client_name": "other"}).json()["client_id"]
            crossed = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": other})
            self.assertNotEqual(crossed.status_code, 200)
            refreshed = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id})
            self.assertEqual(refreshed.status_code, 200, refreshed.text[:400])
            self.assertGreaterEqual(_Upstream.refresh_calls, 1)
            report = self._call(client, refreshed.json()["access_token"], "report_gates")
            self.assertIn('"ok":true', report.replace(" ", ""))
            self.assertIn('"writes_enabled":false', report.replace(" ", ""))

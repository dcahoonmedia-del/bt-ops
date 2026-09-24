"""Review regressions: identity, secret read, query form, ASGI auth. No live calls."""

from __future__ import annotations

import logging
import asyncio
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import parse_qs, urlparse

import jwt
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

from bt_fieldwork_write_mcp.config import SECRET_RESOURCE
from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.fieldwork import FakeTransport, HttpTransport, TypedFieldworkClient, occurrence_ids
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey, read_one_secret
from bt_fieldwork_write_mcp.server import build_mcp, request_identity
from bt_fieldwork_write_mcp.__main__ import main
from tests.test_write_mcp import IDENTITY, Harness, _settings


class _Payload:
    def __init__(self, data: bytes) -> None:
        self.data = data


class _Response:
    def __init__(self, data: bytes) -> None:
        self.payload = _Payload(data)


class _Boom:
    def access_secret_version(self, request: dict) -> None:
        raise RuntimeError("projects/bt-intake-proof/secrets/BT-fieldworks-key secret=super")


class ReviewTests(unittest.TestCase):
    def test_cross_customer_ids_do_not_propose(self) -> None:
        h = Harness()
        loc = h.transport.locations["41:77"]
        loc["id"] = 88
        loc["customer_id"] = 999
        result = h.propose_notes()
        self.assertFalse(result["ok"])
        self.assertEqual(result["gate"], "identity_mismatch")
        self.assertFalse(any(call["method"] == "PATCH" for call in h.transport.calls))
        h.close()

    def test_customer_wrapper_fails_closed(self) -> None:
        class Wrap(FakeTransport):
            def request(self, method, path, body=None, query=None):
                if method == "GET" and path == "/customers/41":
                    return 200, {"customer": {"id": 41, "customer_status": "Active"}}
                return super().request(method, path, body, query)

        client = TypedFieldworkClient(Wrap())
        with self.assertRaises(GateError) as caught:
            client.get_customer("41")
        self.assertEqual(caught.exception.gate, "customer_shape_unverified")

    def test_secret_exception_is_sanitized(self) -> None:
        try:
            read_one_secret(_Boom())
        except GateError as exc:
            self.assertEqual(exc.gate, "secret_read_failed")
            self.assertNotIn("super", str(exc))
            self.assertNotIn("BT-fieldworks", str(exc))
        else:
            self.fail("expected gate")
        class _Client:
            def access_secret_version(self, request: dict) -> _Response:
                return _Response(b"in-memory-only")

        key = read_one_secret(_Client())
        self.assertIsInstance(key, InMemoryApiKey)
        self.assertNotIn("in-memory-only", repr(key))

    def test_repeated_form_and_allowed_query(self) -> None:
        seen = {}

        class Cap:
            def open(self, req, timeout=30):
                seen["url"] = req.full_url
                seen["body"] = req.data
                class R:
                    status = 200
                    def read(self):
                        return b"{}"
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        return False
                return R()

        transport = HttpTransport(InMemoryApiKey("hidden-key"), opener=Cap())
        transport.request(
            "POST",
            "/work_orders?api_key=nope&evil=1",
            {"service_route_ids": [1, 2]},
            query={"per_page": 1, "api_key": "override", "drop": "x"},
        )
        parsed = parse_qs(urlparse(seen["url"]).query)
        self.assertEqual(parsed["api_key"], ["hidden-key"])
        self.assertEqual(parsed["per_page"], ["1"])
        self.assertNotIn("evil", parsed)
        self.assertNotIn("drop", parsed)
        self.assertEqual(seen["body"].decode().count("service_route_ids"), 2)

    def test_arrival_display_key(self) -> None:
        ids = occurrence_ids({"appointment_occurrence": {"id": 1, "service_appointment_id": 2, "arrival_time_window_str": "1-5"}})
        self.assertEqual(ids["arrival_time_window_str"], "1-5")

    def test_request_context_identity_and_inspect(self) -> None:
        h = Harness()
        proposed = h.propose_notes()
        verifier = JwtTokenVerifier(h.settings)
        server = build_mcp(h.service, h.settings, verifier)
        self.assertIsNone(request_identity())
        from mcp.server.auth.provider import AccessToken

        user = AuthenticatedUser(
            AccessToken(
                token="[redacted]",
                client_id="c",
                scopes=["fieldwork.write"],
                expires_at=9999999999,
                resource=h.settings.oauth_resource,
                subject="user-1",
                claims={"email": "daniel@btpestcontrol.com"},
            )
        )
        token = auth_context_var.set(user)
        try:
            self.assertEqual(request_identity(), IDENTITY)
            listed = asyncio.run(server.call_tool("inspect_proposal", {"proposal_id": proposed["proposal_id"]}))
        finally:
            auth_context_var.reset(token)
        text = str(listed)
        self.assertIn(proposed["proposal_id"], text)
        self.assertNotIn("operator-test-key", text)
        h.close()

    def test_http_startup_fails_without_oauth(self) -> None:
        env = os.environ.copy()
        os.environ["FW_WRITE_TRANSPORT"] = "http"
        os.environ["FW_WRITE_OAUTH_ISSUER"] = ""
        os.environ["FW_WRITE_STORE"] = "/var/lib/bt-fieldwork-write-mcp/write.sqlite"
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    main()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("oauth_required", stderr.getvalue())
            self.assertIn("fieldwork_get_protocol_historically_verified", stderr.getvalue())
            self.assertIn("fieldwork_get_auth_verified': False", stderr.getvalue())
        finally:
            os.environ.clear()
            os.environ.update(env)

    def test_asgi_tools_call_requires_verified_bearer(self) -> None:
        from datetime import datetime, timedelta, timezone

        logging.disable(logging.INFO)
        h = Harness()
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": h.settings.oauth_issuer,
                "aud": h.settings.oauth_audience,
                "sub": "user-1",
                "email": "daniel@btpestcontrol.com",
                "scope": "fieldwork.write",
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            h.settings.hs256_secret,
            algorithm="HS256",
        )
        server = build_mcp(h.service, h.settings, JwtTokenVerifier(h.settings))
        app = server.streamable_http_app(
            json_response=True,
            stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        with TestClient(app) as client:
            denied = client.post("/mcp", headers={"Accept": headers["Accept"], "Content-Type": "application/json"}, json=init)
            self.assertEqual(denied.status_code, 401)
            self.assertNotIn(h.settings.hs256_secret, denied.text)
            opened = client.post("/mcp", headers=headers, json=init)
            self.assertEqual(opened.status_code, 200, opened.text[:300])
            session = opened.headers.get("mcp-session-id")
            call_headers = dict(headers)
            if session:
                call_headers["mcp-session-id"] = session
            client.post("/mcp", headers=call_headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            called = client.post(
                "/mcp",
                headers=call_headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "inspect_proposal", "arguments": {"proposal_id": "missing"}}},
            )
            self.assertEqual(called.status_code, 200, called.text[:400])
            self.assertNotIn("oauth_rejected", called.text)
            self.assertIn("unknown_operation", called.text)
            proposed = client.post(
                "/mcp",
                headers=call_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "propose_write",
                        "arguments": {
                            "operation": "update_service_location_notes",
                            "payload": {"customer_id": 41, "location_id": 77, "notes": "standing note"},
                        },
                    },
                },
            )
            self.assertEqual(proposed.status_code, 200, proposed.text[:500])
            self.assertIn("proposal_id", proposed.text)
            self.assertNotIn("oauth_rejected", proposed.text)
            self.assertNotIn(h.settings.hs256_secret, proposed.text)
            self.assertFalse(any(call["method"] == "PATCH" for call in h.transport.calls))
        logging.disable(logging.NOTSET)
        h.close()

    def test_module_entry_exits_without_oauth_on_stderr(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "/workspace/security/bt-fieldwork-write-mcp/src"
        env["FW_WRITE_TRANSPORT"] = "http"
        env["FW_WRITE_OAUTH_ISSUER"] = ""
        env.pop("FW_WRITE_OAUTH_HS256", None)
        proc = subprocess.run(
            [sys.executable, "-m", "bt_fieldwork_write_mcp"],
            cwd="/workspace/security/bt-fieldwork-write-mcp",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("oauth_required", proc.stderr)

    def test_entry_import(self) -> None:
        import bt_fieldwork_write_mcp.server as server

        self.assertTrue(hasattr(server, "build_server"))
        self.assertEqual(SECRET_RESOURCE.rsplit("/", 1)[-1], "latest")

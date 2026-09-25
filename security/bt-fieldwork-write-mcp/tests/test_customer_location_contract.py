"""Caller location contract versus the Fieldwork customer POST. No live calls."""

from __future__ import annotations

import asyncio
import io
import json
import unittest
from urllib.parse import parse_qsl
from urllib.request import Request

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from bt_fieldwork_write_mcp.create_contract import customer_request
from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from bt_fieldwork_write_mcp.server import build_mcp
from tests.test_write_mcp import IDENTITY, Harness


def _john(**extra: object) -> dict:
    payload = {
        "customer_type": "Residential",
        "first_name": "John",
        "last_name": "Doe",
        "status": "active",
        "billing_phone": "9103335555",
        "billing_street": "105 Thorn Tree Ct",
        "billing_city": "Jacksonville",
        "billing_state": "NC",
        "service_locations": {"name": "Main Location", "same_as_billing_address": True},
        "contact": {
            "first_name": "John",
            "last_name": "Doe",
            "email": "dcahoonmedia@gmail.com",  # pragma: allowlist secret
            "phone": "9103335555",
        },
        "confirmed_new": True,
    }
    payload.update(extra)
    return payload


def _identity_only() -> dict:
    return {
        "customer_type": "Residential",
        "first_name": "John",
        "last_name": "Doe",
        "status": "active",
        "billing_phone": "9103335555",
        "confirmed_new": True,
    }


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _Opener:
    def __init__(self, body: bytes = b"[]") -> None:
        self.requests: list[Request] = []
        self._body = body

    def open(self, req: Request, timeout: int = 30) -> _Response:
        self.requests.append(req)
        return _Response(self._body)


def _tool_json(result: object) -> dict:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, tuple):
        content = result[0]
    text = content[0].text
    return json.loads(text)


class CustomerLocationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", approval_mode="chatgpt_confirmation")

    def tearDown(self) -> None:
        self.h.close()

    def _mcp(self, payload: dict) -> dict:
        server = build_mcp(self.h.service, self.h.settings, JwtTokenVerifier(self.h.settings))
        user = AuthenticatedUser(
            AccessToken(
                token="[redacted]",
                client_id="c",
                scopes=["fieldwork.write"],
                expires_at=9999999999,
                resource=self.h.settings.oauth_resource,
                subject=IDENTITY["sub"],
                claims={"email": IDENTITY["email"]},
            )
        )
        token = auth_context_var.set(user)
        try:
            result = asyncio.run(server.call_tool("propose_write", {"operation": "create_customer", "payload": payload}))
        finally:
            auth_context_var.reset(token)
        return _tool_json(result)

    def test_identity_only_is_not_an_unknown_service_locations_field(self) -> None:
        proposed = self._mcp(_identity_only())
        self.assertFalse(proposed["ok"])
        self.assertNotEqual(proposed.get("fields"), ["service_locations"])
        self.assertEqual(proposed["gate"], "nested_location_required")
        self.assertFalse(any(call["method"] in {"POST", "PATCH"} for call in self.h.transport.calls))

    def test_john_doe_proposal_shows_steps_and_does_not_mutate(self) -> None:
        before = len(self.h.transport.calls)
        proposed = self._mcp(_john())
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(any(call["method"] in {"POST", "PATCH"} for call in self.h.transport.calls[before:]))
        plan = proposed["after"]["documented_request"]
        customer = plan["customer"]
        self.assertEqual(customer["customer_type"], "Residential")
        self.assertEqual(customer["status"], "active")
        self.assertEqual(customer["first_name"], "John")
        self.assertEqual(customer["last_name"], "Doe")
        self.assertEqual(customer["billing_phone"], "9103335555")
        self.assertEqual(customer["billing_street"], "105 Thorn Tree Ct")
        self.assertEqual(customer["billing_city"], "Jacksonville")
        self.assertEqual(customer["billing_state"], "NC")
        self.assertNotIn("billing_zip", customer)
        self.assertNotIn("service_locations", customer)
        self.assertEqual(
            customer["service_locations_attributes"],
            [{"name": "Main Location", "same_as_billing_address": True}],
        )
        self.assertEqual(plan["contact"]["email"], "dcahoonmedia@gmail.com")  # pragma: allowlist secret
        self.assertTrue(plan["confirmed_new"])
        self.assertEqual(plan["duplicate_resolution"]["candidate_ids"], [])
        steps = plan["api_steps"]
        self.assertEqual(steps[0]["method"], "POST")
        self.assertEqual(steps[0]["path"], "/customers")
        self.assertEqual(steps[0]["body"]["customer"]["service_locations_attributes"][0]["name"], "Main Location")
        self.assertEqual(steps[1]["method"], "POST")
        self.assertEqual(steps[1]["path"], "/customers/{customer_id}/contacts")
        self.assertNotIn("zip", json.dumps(steps))

    def test_same_billing_distinct_address_and_extra_location(self) -> None:
        same_payload = _john()
        same_payload.pop("contact")
        same = self._mcp(same_payload)
        self.assertTrue(same["ok"], same)
        self.assertIsNone(same["after"]["documented_request"]["location_patch"])
        self.assertIsNone(same["after"]["documented_request"]["contact"])
        distinct = self._mcp(
            _john(
                last_name="Distinct",
                service_locations=[{"name": "Main Location", "same_as_billing_address": False}],
                service_address={"street": "9 Other Rd", "city": "Jacksonville", "state": "NC"},
                location_tax_rate_id=7704,
                additional_location={"name": "Shop", "tax_rate_id": 7704, "address": {"street": "2 Side", "city": "Jacksonville", "state": "NC"}},
            )
        )
        self.assertTrue(distinct["ok"], distinct)
        plan = distinct["after"]["documented_request"]
        methods = [(step["method"], step["path"]) for step in plan["api_steps"]]
        self.assertEqual(
            methods,
            [
                ("POST", "/customers"),
                ("PATCH", "/customers/{customer_id}/service_locations/{location_id}"),
                ("POST", "/customers/{customer_id}/service_locations"),
                ("POST", "/customers/{customer_id}/contacts"),
            ],
        )
        nested = plan["customer"]["service_locations_attributes"][0]
        self.assertEqual(nested, {"name": "Main Location", "same_as_billing_address": False})
        self.assertNotIn("address_attributes", nested)
        self.assertNotIn("zip", plan["location_patch"]["address_attributes"])

    def test_repeated_normalization_and_invalid_field(self) -> None:
        raw = _john()
        first = customer_request(raw)
        second = customer_request(raw)
        self.assertEqual(first["customer"], second["customer"])
        self.assertEqual(first["api_steps"], second["api_steps"])
        self.assertIsInstance(raw["service_locations"], dict)
        rejected = self._mcp(_john(email="dcahoonmedia@gmail.com"))  # pragma: allowlist secret
        self.assertEqual(rejected["gate"], "unknown_field")
        self.assertEqual(rejected["fields"], ["email"])

    def test_http_transport_encodes_verified_customer_body(self) -> None:
        plan = customer_request(_john())
        opener = _Opener(b'{"id": 1}')
        client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=opener))
        client.create_customer({"customer": plan["customer"]})
        sent = opener.requests[0]
        self.assertEqual(sent.method, "POST")
        pairs = parse_qsl(sent.data.decode())
        keys = [key for key, _value in pairs]
        self.assertIn("customer[service_locations_attributes][][name]", keys)
        self.assertIn("customer[service_locations_attributes][][same_as_billing_address]", keys)
        self.assertNotIn("customer[service_locations]", keys)
        self.assertNotIn("customer[billing_zip]", keys)
        values = dict(pairs)
        self.assertEqual(values["customer[billing_street]"], "105 Thorn Tree Ct")
        self.assertEqual(values["customer[status]"], "active")
        self.assertNotIn("zip", sent.data.decode())

    def test_approval_and_payload_still_guard_execute(self) -> None:
        proposed = self._mcp(_john())
        self.assertTrue(proposed["ok"], proposed)
        bare = self.h.service.execute(proposed["proposal_id"], IDENTITY, approved=True, expected_digest="0" * 64)
        self.assertEqual(bare["gate"], "operator_approval_required")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/customers" for call in self.h.transport.calls))
        row = self.h.store.get_proposal(proposed["proposal_id"])
        self.h.store._conn.execute(
            "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
            (json.dumps({**row["payload"], "last_name": "Changed"}), proposed["proposal_id"]),
        )
        token = self.h.approve(proposed["proposal_id"])
        tampered = self.h.service.execute(
            proposed["proposal_id"],
            IDENTITY,
            operator_approval=token,
            approved=True,
            expected_digest=proposed["digest"],
        )
        self.assertFalse(tampered["ok"])
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/customers" for call in self.h.transport.calls))

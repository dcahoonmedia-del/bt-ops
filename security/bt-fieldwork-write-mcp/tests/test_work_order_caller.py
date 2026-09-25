"""Caller schedule and quoted initial price. No live Fieldwork calls."""

from __future__ import annotations

import asyncio
import json
import unittest
from urllib.parse import parse_qsl

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from bt_fieldwork_write_mcp.server import build_mcp
from tests.test_customer_location_contract import _Opener, _tool_json
from tests.test_write_mcp import IDENTITY, Harness


def _line(price: int) -> dict:
    return {
        "name": "PestGuard - Set-up",
        "type": "service",
        "quantity": 1,
        "price": price,
        "payable_id": 38814,
        "payable_type": "Service",
        "taxable": False,
    }


def _flat(**extra: object) -> dict:
    payload = {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "starts_at": "2026-10-02",
        "duration": 60,
        "service_route_ids": [1],
        "instructions": "Initial only",
    }
    payload.update(extra)
    return payload


class WorkOrderCallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer", approval_mode="chatgpt_confirmation")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }, {
            "id": 11, "first_name": "Daniel", "last_name": "Route", "email": "route@example.test",
            "service_route_id": 2557, "service_route_name": "Route 3", "is_technician": True, "branches": [],
        }]

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
            result = asyncio.run(server.call_tool("propose_write", {"operation": "create_work_order", "payload": payload}))
        finally:
            auth_context_var.reset(token)
        return _tool_json(result)

    def test_minimal_ids_are_missing_fields_not_unknown_occurrences(self) -> None:
        missing = self._mcp({"customer_id": 41, "service_location_id": 77})
        self.assertEqual(missing["gate"], "missing_field")
        self.assertEqual(missing["fields"], ["starts_at", "service_route_ids"])
        self.assertNotEqual(missing.get("fields"), ["occurrences"])

    def test_flat_caller_and_standard_price_stay_on_the_proposal(self) -> None:
        proposed = self._mcp(_flat())
        self.assertTrue(proposed["ok"], proposed)
        pricing = proposed["after"]["service_pricing"]
        self.assertEqual(pricing["price_source"], "template_standard")
        self.assertEqual(pricing["price"], proposed["after"]["catalog"]["line"]["price"])
        self.assertEqual(pricing["total"], pricing["price"])
        self.assertEqual(proposed["after"]["production_value"], pricing["price"])
        self.assertTrue(proposed["after"]["initial_treatment_only"])
        self.assertFalse(proposed["after"]["recurrence"])
        self.assertFalse(proposed["after"]["agreement"])
        body = proposed["after"]["documented_request"]["service_appointment"]
        self.assertEqual(body["appointment_occurrences_attributes"][0]["starts_at"], "2026-10-02")
        self.assertEqual(body["line_items_attributes"][0]["price"], pricing["price"])
        self.assertEqual(len(body["line_items_attributes"]), 1)
        self.assertIsNone(proposed["after"]["schedule_patch"])

    def test_quoted_price_is_not_replaced_by_the_template(self) -> None:
        standard = self._mcp(_flat())
        quoted = self._mcp(_flat(line_items=[_line(175)], starts_at="2026-10-03"))
        self.assertTrue(quoted["ok"], quoted)
        self.assertEqual(quoted["after"]["price_source"], "caller")
        self.assertEqual(quoted["after"]["price"], 175)
        self.assertEqual(quoted["after"]["line_total"], 175)
        self.assertEqual(quoted["after"]["production_value"], 175)
        self.assertEqual(quoted["after"]["standard_price"], standard["after"]["standard_price"])
        self.assertNotEqual(quoted["digest"], standard["digest"])
        line = quoted["after"]["documented_request"]["service_appointment"]["line_items_attributes"][0]
        self.assertEqual(line["price"], 175)
        self.assertEqual(line["name"], "PestGuard - Set-up")
        done = self.h.service.execute(quoted["proposal_id"], IDENTITY, approved=True, expected_digest=quoted["digest"])
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["price"], 175)
        self.assertEqual(done["readback"]["line_total"], 175)
        self.assertEqual(done["readback"]["production_value"], 175)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["body"]["service_appointment"]["line_items_attributes"][0]["price"], 175)

    def test_offset_and_dst_keep_one_post_and_one_patch(self) -> None:
        edt = self._mcp(_flat(starts_at="2026-10-02T14:00:00-04:00", service_route_ids=[2557]))
        self.assertTrue(edt["ok"], edt)
        self.assertEqual(edt["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]["starts_at"], "2026-10-02")
        self.assertEqual(edt["after"]["schedule_patch"]["starts_at"], "2026-10-02T14:00:00-04:00")
        self.assertEqual(edt["after"]["schedule_patch"]["service_route_ids"], [2557])
        est = self._mcp(_flat(starts_at="2026-12-02T14:00:00-05:00"))
        self.assertEqual(est["after"]["schedule_patch"]["starts_at"], "2026-12-02T14:00:00-05:00")
        self.assertEqual(est["after"]["starts_at_timezone"], "-05:00")
        mixed = self._mcp(_flat(occurrences=[{"service_route_ids": [1], "starts_at": "2026-10-04"}], starts_at="2026-10-04"))
        self.assertEqual(mixed["gate"], "unknown_field")
        self.assertIn("starts_at", mixed["fields"])

    def test_http_serializer_uses_the_approved_price_and_date(self) -> None:
        proposed = self._mcp(_flat(line_items=[_line(175)], starts_at="2026-10-02T14:00:00-04:00"))
        body = proposed["after"]["documented_request"]
        opener = _Opener(b'{"id": 9, "service_appointment_id": 10}')
        client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=opener))
        client.create_work_order(body)
        pairs = parse_qsl(opener.requests[0].data.decode())
        values = dict(pairs)
        self.assertEqual(values["service_appointment[appointment_occurrences_attributes][][starts_at]"], "2026-10-02")
        self.assertEqual(values["service_appointment[line_items_attributes][][price]"], "175")
        self.assertEqual(values["service_appointment[line_items_attributes][][name]"], "PestGuard - Set-up")
        self.assertEqual(values["service_appointment[repeat_type]"], "none")
        self.assertNotIn("service_appointment[appointment_occurrences_attributes][][use_time_window]", values)
        joined = opener.requests[0].data.decode()
        self.assertNotIn("2026-10-02T14:00:00-04:00", joined)
        self.assertEqual(sum(1 for key, _value in pairs if key.endswith("[price]")), 1)

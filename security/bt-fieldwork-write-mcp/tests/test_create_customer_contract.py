"""Discoverability of the create_customer coverage acknowledgment. Offline only."""

from __future__ import annotations

import asyncio
import unittest

from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
from bt_fieldwork_write_mcp.server import CREATE_CUSTOMER_EXAMPLE, PROPOSE_DESCRIPTION, build_mcp
from tests.test_write_mcp import IDENTITY, Harness


class CreateCustomerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")

    def tearDown(self) -> None:
        self.h.close()

    def test_missing_acknowledgment_returns_the_exact_retry(self) -> None:
        payload = {key: value for key, value in CREATE_CUSTOMER_EXAMPLE.items() if key != "acknowledge_duplicate_coverage"}
        blocked = self.h.service.propose("create_customer", payload, IDENTITY)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["reason"], "coverage_acknowledgment_required")
        self.assertEqual(blocked["field"], "acknowledge_duplicate_coverage")
        self.assertEqual(blocked["required_value"], ["address", "email"])
        self.assertEqual(blocked["retry_example"], {"acknowledge_duplicate_coverage": ["address", "email"]})
        self.assertIn("unsupported or incomplete", blocked["instructions"])
        self.assertIn("does not assert that searches succeeded", blocked["instructions"])
        self.assertNotIn("searches succeeded", blocked["acknowledgment_effect"])
        self.assertEqual(blocked["does_not_assert"], "searches_succeeded_or_no_duplicate")
        self.assertFalse(any(call["method"] in {"POST", "PATCH", "PUT", "DELETE"} for call in self.h.transport.calls))

    def test_exact_acknowledgment_stays_incomplete_and_a_wrong_list_fails(self) -> None:
        exact = dict(CREATE_CUSTOMER_EXAMPLE)
        exact["acknowledge_duplicate_coverage"] = ["email", "address"]
        proposed = self.h.service.propose("create_customer", exact, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        search = proposed["after"]["duplicate_search"]
        self.assertFalse(search["complete"])
        self.assertFalse(search["no_duplicate_claim"])
        self.assertEqual(search["coverage_gap"], ["address", "email"])
        self.assertFalse(proposed["live_tested"])
        self.assertFalse(proposed["response_schema_verified"])
        claimed = dict(CREATE_CUSTOMER_EXAMPLE)
        claimed["duplicate_search_complete"] = True
        rejected = self.h.service.propose("create_customer", claimed, IDENTITY)
        self.assertEqual(rejected["gate"], "unknown_field")
        wrong = dict(CREATE_CUSTOMER_EXAMPLE)
        wrong["last_name"] = "Wrong"
        wrong["acknowledge_duplicate_coverage"] = ["email"]
        missed = self.h.service.propose("create_customer", wrong, IDENTITY)
        self.assertEqual(missed["reason"], "coverage_acknowledgment_required")
        self.assertEqual(missed["required_value"], ["address", "email"])
        self.assertNotEqual(missed["retry_example"]["acknowledge_duplicate_coverage"], ["email"])

    def test_canonical_payload_proposes_an_active_customer_without_a_contact_or_a_write(self) -> None:
        before = len(self.h.transport.calls)
        proposed = self.h.service.propose("create_customer", dict(CREATE_CUSTOMER_EXAMPLE), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(any(call["method"] in {"POST", "PATCH", "PUT", "DELETE"} for call in self.h.transport.calls[before:]))
        plan = proposed["after"]["documented_request"]
        self.assertEqual(plan["customer"]["status"], "active")
        self.assertIsNone(plan["contact"])
        self.assertEqual(proposed["after"]["contact_count"], 0)
        self.assertEqual(plan["primary_email"], "ada@example.test")
        self.assertNotIn("invoice_email", plan["customer"])
        self.assertFalse(proposed["live_tested"])
        self.assertFalse(proposed["after"]["response_schema_verified"])
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["status"], "active")
        self.assertEqual(done["readback"]["contact_count"], 0)
        self.assertFalse(done["readback"]["response_schema_verified"])
        self.assertFalse(any(call["method"] == "POST" and call["path"].endswith("/contacts") for call in self.h.transport.calls))

    def test_new_duplicate_match_still_blocks_execution(self) -> None:
        payload = dict(CREATE_CUSTOMER_EXAMPLE)
        payload["last_name"] = "Later"
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.h.transport.add_customer(
            {"id": 90, "name": "Later", "last_name": "Later", "customer_status": "Active", "status": "active"},
            {"id": 91, "name": "Main Location", "same_as_billing_address": True, "address": {"id": 4}},
        )
        denied = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertEqual(denied["gate"], "duplicate_unresolved")
        self.assertEqual(denied["reason"], "new_match_requires_approval")
        self.assertFalse(any(call["method"] == "POST" and call["path"] == "/customers" for call in self.h.transport.calls))

    def test_tools_list_publishes_the_current_create_customer_contract(self) -> None:
        server = build_mcp(self.h.service, self.h.settings, JwtTokenVerifier(self.h.settings))
        tools = asyncio.run(server.list_tools())
        propose = next(tool for tool in tools if tool.name == "propose_write")
        self.assertEqual(propose.description, PROPOSE_DESCRIPTION)
        text = propose.description
        self.assertIn("primary_email", text)
        self.assertIn("acknowledge_duplicate_coverage", text)
        self.assertIn("billing_street", text)
        self.assertIn("service_locations", text)
        self.assertIn("ada@example.test", text)
        self.assertIn("separately requested additional contact", text)
        self.assertIn("not live-tested", text)
        self.assertIn("does not mark creation or response schemas live-verified", text)
        self.assertNotIn("email is contact.email only", text)
        self.assertIn("acknowledge_duplicate_coverage", server.instructions)
        self.assertIn("primary_email", server.instructions)

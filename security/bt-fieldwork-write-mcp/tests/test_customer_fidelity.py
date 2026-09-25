"""Customer email, phone, location type, and duplicate coverage. No live calls."""

from __future__ import annotations

import unittest
from urllib.parse import parse_qsl

from bt_fieldwork_write_mcp.create_contract import customer_request
from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey
from tests.test_customer_location_contract import _Opener
from tests.test_write_mcp import IDENTITY, Harness


def _home(**extra: object) -> dict:
    payload = {
        "customer_type": "Residential",
        "last_name": "Ng",
        "service_locations": {"name": "Main Location", "same_as_billing_address": True},
    }
    payload.update(extra)
    return payload


class CustomerFidelityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")

    def tearDown(self) -> None:
        self.h.close()

    def test_phone_kind_is_passed_through_and_omission_is_explicit(self) -> None:
        proposed = self.h.service.propose("create_customer", _home(billing_phone="9105550100", billing_phone_kind="Home"), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["billing_phone_kind"], "Home")
        self.assertTrue(proposed["after"]["phone_kind_supplied"])
        unknown = self.h.service.propose("create_customer", _home(last_name="Kind", billing_phone_kind="Cell"), IDENTITY)
        self.assertEqual(unknown["gate"], "unknown_field")
        omitted = self.h.service.propose("create_customer", _home(last_name="Plain", billing_phone="9105550101"), IDENTITY)
        self.assertTrue(omitted["ok"], omitted)
        self.assertFalse(omitted["after"]["phone_kind_supplied"])
        self.assertNotIn("billing_phone_kind", omitted["after"]["documented_request"]["customer"])

    def test_residential_uses_configured_type_and_commercial_is_explicit(self) -> None:
        proposed = self.h.service.propose("create_customer", _home(), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["location_type_id"], 8736)
        self.assertEqual(proposed["after"]["property_type"], "Residential")
        self.assertEqual(proposed["after"]["reminders_type"], 0)
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", residential_location_type_id="")
        missing = self.h.service.propose("create_customer", _home(last_name="Unset"), IDENTITY)
        self.assertEqual(missing["gate"], "location_type_unconfigured")
        commercial = self.h.service.propose("create_customer", {"customer_type": "Commercial", "name": "Shop", "service_locations": {"name": "Shop", "same_as_billing_address": True}}, IDENTITY)
        self.assertEqual(commercial["gate"], "location_type_required")

    def test_primary_email_is_not_a_contact_and_does_not_post(self) -> None:
        proposed = self.h.service.propose("create_customer", _home(primary_email="ada@example.test"), IDENTITY)
        self.assertEqual(proposed["gate"], "duplicate_search_incomplete")
        self.assertEqual(proposed["reason"], "email_or_address_coverage_gap")
        self.assertEqual(proposed["coverage_gap"], ["email"])
        self.assertEqual(proposed["after"]["contact_count"] if proposed.get("after") else 0, 0)
        plan = customer_request(_home(primary_email="ada@example.test"))
        self.assertIsNone(plan["contact"])
        self.assertEqual(plan["invoice_email"]["write_supported"], False)
        self.assertNotIn("invoice_email", plan["customer"])
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        explicit = customer_request(_home(contact={"first_name": "Ada", "last_name": "Ng", "email": "ada@example.test"}))
        self.assertEqual(explicit["contact_count"], 1)
        self.assertNotEqual(explicit["contact"]["email"], explicit.get("primary_email"))

    def test_location_patch_serializes_documented_fields_only(self) -> None:
        plan = customer_request(_home(location_email="reports@example.test"))
        from bt_fieldwork_write_mcp.creation_flow import bind_residential_location

        bind_residential_location(plan, self.h.client, "8736")
        step = next(item for item in plan["api_steps"] if item["method"] == "PATCH")
        opener = _Opener(b'{"service_location":{"id":1}}')
        client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=opener))
        client.patch_service_location("41", "77", step["body"])
        values = dict(parse_qsl(opener.requests[0].data.decode()))
        self.assertEqual(values["service_location[email]"], "reports@example.test")
        self.assertEqual(values["service_location[location_type_id]"], "8736")
        self.assertEqual(values["service_location[reminders_type]"], "0")
        self.assertNotIn("service_location[send_report_email]", values)
        self.assertIn("inherited_send_report_email_true_may_send_once_location_email_is_added", plan["notification_effects"]["completion_report"])
        self.assertIn("does_not_disable_every_notice", plan["notification_effects"]["appointment_reminders"])

    def test_omitted_reminder_readback_is_unverified_and_a_mismatch_is_not_success(self) -> None:
        proposed = self.h.service.propose("create_customer", _home(billing_phone_kind="Mobile"), IDENTITY)
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["reminders_type"]["status"], "unverified")
        self.assertNotEqual(done["readback"]["reminders_type"].get("value"), False)
        location_id = str(done["readback"]["location_id"])
        customer_id = str(done["readback"]["customer_id"])
        self.h.transport.locations[f"{customer_id}:{location_id}"]["reminders_type"] = 1
        from bt_fieldwork_write_mcp.creation_flow import customer_readback
        from bt_fieldwork_write_mcp.errors import GateError

        with self.assertRaises(GateError) as caught:
            customer_readback(self.h.client, customer_id, sent_customer=proposed["after"]["documented_request"]["customer"], contact=None, location_id=location_id, address=None, main_location=proposed["after"]["documented_request"]["main_location"])
        self.assertEqual(caught.exception.detail["field"], "reminders_type")

    def test_address_coverage_gap_blocks_create_and_an_extra_field_does_not_skip_it(self) -> None:
        blocked = self.h.service.propose("create_customer", _home(billing_street="9 Billing", billing_city="Buffalo", billing_state="NY"), IDENTITY)
        self.assertEqual(blocked["reason"], "email_or_address_coverage_gap")
        self.assertIn("address", blocked["coverage_gap"])
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        bypass = self.h.service.propose("create_customer", _home(invoice_email="ada@example.test"), IDENTITY)
        self.assertEqual(bypass["gate"], "unknown_field")
        self.assertEqual(bypass["fields"], ["invoice_email"])

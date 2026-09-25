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
        blocked = self.h.service.propose("create_customer", _home(primary_email="ada@example.test", confirmed_new=True), IDENTITY)
        self.assertEqual(blocked["reason"], "coverage_acknowledgment_required")
        self.assertEqual(blocked["coverage_gap"], ["email"])
        self.assertFalse(blocked.get("duplicate_search", {}).get("complete", False))
        proposed = self.h.service.propose("create_customer", _home(primary_email="ada@example.test", acknowledge_duplicate_coverage=["email"]), IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertFalse(proposed["after"]["duplicate_search"]["complete"])
        self.assertFalse(proposed["after"]["duplicate_search"]["no_duplicate_claim"])
        self.assertEqual(proposed["after"]["contact_count"], 0)
        self.assertFalse(proposed["after"]["invoice_email"]["post_supported"])
        self.assertTrue(proposed["after"]["invoice_email"]["patch_supported"])
        self.assertNotIn("invoice_email", proposed["after"]["documented_request"]["customer"])
        invoice_step = next(item for item in proposed["after"]["documented_request"]["api_steps"] if item["path"] == "/customers/{customer_id}")
        self.assertEqual(invoice_step, {"method": "PATCH", "path": "/customers/{customer_id}", "body": {"customer": {"invoice_email": "ada@example.test"}}})
        self.assertEqual(proposed["after"]["invoice_email"]["value"], "ada@example.test")
        self.assertEqual(proposed["after"]["invoice_email"]["sole_form_field"], "customer[invoice_email]")
        self.assertEqual(proposed["after"]["notification_effects"]["invoice_email_notice_delivery"], "not_audited")
        self.assertEqual(proposed["after"]["notification_effects"]["same_as_billing_invoice_email_propagation"], "observed_once_not_proven_for_other_locations")
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["primary_email"]["status"], "verified")
        self.assertEqual(done["readback"]["primary_email"]["value"], "ada@example.test")
        self.assertEqual(done["readback"]["location_email"]["value"], "ada@example.test")
        self.assertEqual(done["readback"]["contact_count"], 0)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers"]
        self.assertEqual(len(posts), 1)
        self.assertNotIn("invoice_email", posts[0]["body"]["customer"])
        invoice_patches = [call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].startswith("/customers/") and call["path"].count("/") == 2]
        self.assertEqual(len(invoice_patches), 1)
        self.assertEqual(invoice_patches[0]["body"], {"customer": {"invoice_email": "ada@example.test"}})
        self.assertFalse(any(call["method"] == "POST" and call["path"].endswith("/contacts") for call in self.h.transport.calls))
        journal = self.h.service.store.creation_journal(proposed["proposal_id"])
        invoice_rows = [row for row in journal if row["step"] == "invoice_email_patch"]
        self.assertEqual(len(invoice_rows), 1)
        self.assertEqual(invoice_rows[0]["outcome"], "succeeded")
        self.assertEqual(invoice_rows[0]["intent"], {"customer": {"invoice_email": "ada@example.test"}})
        plan = customer_request(_home(primary_email="ada@example.test"))
        self.assertIsNone(plan["contact"])
        self.assertFalse(plan["invoice_email"]["post_supported"])
        self.assertNotIn("invoice_email", plan["customer"])
        explicit = self.h.service.propose(
            "create_customer",
            _home(last_name="Extra", primary_email="ada@example.test", contact={"first_name": "Ada", "last_name": "Ng", "email": "ada@example.test"}, acknowledge_duplicate_coverage=["email"], confirmed_new=True),
            IDENTITY,
        )
        self.assertTrue(explicit["ok"], explicit)
        self.assertEqual(explicit["after"]["contact_count"], 1)
        explicit_done = self.h.service.execute(explicit["proposal_id"], IDENTITY, operator_approval=self.h.approve(explicit["proposal_id"]))
        self.assertTrue(explicit_done["ok"], explicit_done)
        self.assertEqual(explicit_done["readback"]["contact"]["email"], "ada@example.test")
        self.assertEqual(explicit_done["readback"]["contact_count"], 1)
        differing = self.h.service.propose(
            "create_customer",
            _home(last_name="Split", primary_email="ada@example.test", location_email="reports@example.test", acknowledge_duplicate_coverage=["email"], confirmed_new=True),
            IDENTITY,
        )
        self.assertTrue(differing["ok"], differing)
        self.assertEqual(differing["after"]["notification_effects"]["same_as_billing_invoice_email_propagation"], "observed_once_not_proven_for_other_locations")
        self.assertEqual(differing["after"]["documented_request"]["deferred_location_email"], "reports@example.test")
        before_split = len(self.h.transport.calls)
        split_done = self.h.service.execute(differing["proposal_id"], IDENTITY, operator_approval=self.h.approve(differing["proposal_id"]))
        self.assertTrue(split_done["ok"], split_done)
        self.assertEqual(split_done["readback"]["primary_email"]["value"], "ada@example.test")
        self.assertEqual(split_done["readback"]["location_email"]["value"], "reports@example.test")
        self.assertEqual(split_done["readback"]["contact_count"], 0)
        split_calls = self.h.transport.calls[before_split:]
        invoice_at = next(index for index, call in enumerate(split_calls) if call["method"] == "PATCH" and call["body"] == {"customer": {"invoice_email": "ada@example.test"}})
        restore_at = next(index for index, call in enumerate(split_calls) if call["method"] == "PATCH" and call["body"] == {"service_location": {"email": "reports@example.test"}})
        self.assertLess(invoice_at, restore_at)
        self.assertEqual(len([call for call in split_calls if call["method"] == "PATCH" and call["path"].count("/") == 2]), 1)
        opener = _Opener(b'{"id": 41}')
        from bt_fieldwork_write_mcp.fieldwork import HttpTransport, TypedFieldworkClient
        from bt_fieldwork_write_mcp.secrets import InMemoryApiKey

        client = TypedFieldworkClient(HttpTransport(InMemoryApiKey("hidden-key"), opener=opener))
        client.patch_customer_invoice_email("41", "ada@example.test")
        values = dict(parse_qsl(opener.requests[0].data.decode()))
        self.assertEqual(values, {"customer[invoice_email]": "ada@example.test"})

    def test_invoice_email_patch_does_not_repeat_after_timeout_204_or_mismatch(self) -> None:
        from bt_fieldwork_write_mcp.errors import AmbiguousWriteError

        payload = _home(last_name="Timeout", primary_email="ada@example.test", acknowledge_duplicate_coverage=["email"])
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        original = self.h.transport.request

        def drop_invoice(method, path, body=None, query=None):
            if method == "PATCH" and path.count("/") == 2 and path.startswith("/customers/"):
                self.h.transport.calls.append({"method": method, "path": path, "body": body, "query": query})
                raise AmbiguousWriteError("timeout_after_apply")
            return original(method, path, body, query)

        self.h.transport.request = drop_invoice
        failed = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.h.transport.request = original
        self.assertEqual(failed["retry"], False)
        self.assertIsNotNone(failed["partial"]["customer_id"])
        self.assertIsNotNone(failed["partial"]["location_id"])
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].count("/") == 2]), 1)
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertEqual(again["gate"], "ambiguous_remote_write_no_retry")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].count("/") == 2]), 1)

        accepted = self.h.service.propose("create_customer", _home(last_name="Empty", primary_email="ada@example.test", acknowledge_duplicate_coverage=["email"]), IDENTITY)
        original = self.h.transport.request

        def empty_ok(method, path, body=None, query=None):
            status, payload_body = original(method, path, body, query)
            if method == "PATCH" and path.count("/") == 2 and path.startswith("/customers/"):
                return 204, None
            return status, payload_body

        self.h.transport.request = empty_ok
        done = self.h.service.execute(accepted["proposal_id"], IDENTITY, operator_approval=self.h.approve(accepted["proposal_id"]))
        self.h.transport.request = original
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["primary_email"]["value"], "ada@example.test")

        mismatched = self.h.service.propose("create_customer", _home(last_name="Wrong", primary_email="ada@example.test", acknowledge_duplicate_coverage=["email"], confirmed_new=True), IDENTITY)
        original = self.h.transport.request

        def wrong_email(method, path, body=None, query=None):
            status, payload_body = original(method, path, body, query)
            if method == "PATCH" and path.count("/") == 2 and path.startswith("/customers/"):
                self.h.transport.customers[path.rsplit("/", 1)[-1]]["invoice_email"] = "other@example.test"
            return status, payload_body

        self.h.transport.request = wrong_email
        missed = self.h.service.execute(mismatched["proposal_id"], IDENTITY, operator_approval=self.h.approve(mismatched["proposal_id"]))
        self.h.transport.request = original
        self.assertFalse(missed["ok"])
        self.assertEqual(missed["retry"], False)
        self.assertIsNotNone(missed["partial"]["customer_id"])
        self.assertIsNotNone(missed["partial"]["location_id"])
        before = len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].count("/") == 2])
        replay = self.h.service.execute(mismatched["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertNotEqual(replay.get("ok"), True)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and call["path"].count("/") == 2]), before)

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
        self.assertEqual(done["readback"]["location_type_id"]["status"], "verified")
        self.assertEqual(done["readback"]["location_type_id"]["value"], 8736)
        self.assertEqual(done["readback"]["primary_email"]["status"], "not_sent")
        self.assertEqual(done["readback"]["billing_phone_kind"]["status"], "verified")
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
        blocked = self.h.service.propose("create_customer", _home(billing_street="9 Billing", billing_city="Buffalo", billing_state="NY", confirmed_new=True), IDENTITY)
        self.assertEqual(blocked["reason"], "coverage_acknowledgment_required")
        self.assertIn("address", blocked["coverage_gap"])
        allowed = self.h.service.propose("create_customer", _home(last_name="Street", billing_street="9 Billing", billing_city="Buffalo", billing_state="NY", acknowledge_duplicate_coverage=["address"]), IDENTITY)
        self.assertTrue(allowed["ok"], allowed)
        self.assertEqual(allowed["after"]["duplicate_search"]["searched_fields"], ["name", "phone"])
        self.assertEqual(allowed["after"]["duplicate_search"]["unsearched_fields"], ["address"])
        both = self.h.service.propose(
            "create_customer",
            _home(last_name="Both", primary_email="ada@example.test", billing_street="9 Billing", billing_city="Buffalo", billing_state="NY", acknowledge_duplicate_coverage=["email", "address"]),
            IDENTITY,
        )
        self.assertTrue(both["ok"], both)
        self.assertFalse(both["after"]["duplicate_search"]["complete"])
        self.assertEqual(both["after"]["duplicate_search"]["coverage_gap"], ["address", "email"])
        self.assertFalse(both["after"]["duplicate_search"]["no_duplicate_claim"])
        self.assertFalse(any(call["method"] == "POST" for call in self.h.transport.calls))
        bypass = self.h.service.propose("create_customer", _home(invoice_email="ada@example.test"), IDENTITY)
        self.assertEqual(bypass["gate"], "unknown_field")
        self.assertEqual(bypass["fields"], ["invoice_email"])

    def test_location_settings_204_is_verified_and_ambiguous_patch_is_not_resent(self) -> None:
        from bt_fieldwork_write_mcp.errors import AmbiguousWriteError

        payload = _home(last_name="Report", location_email="reports@example.test", billing_phone_kind="Office", acknowledge_duplicate_coverage=["email"])
        proposed = self.h.service.propose("create_customer", payload, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["billing_phone_kind"], "Office")
        self.assertEqual(proposed["after"]["reminders_type"], 0)
        self.assertEqual(proposed["after"]["contact_count"], 0)
        step = next(item for item in proposed["after"]["documented_request"]["api_steps"] if item["method"] == "PATCH")
        self.assertEqual(step["body"]["service_location"]["email"], "reports@example.test")
        self.assertEqual(step["body"]["service_location"]["reminders_type"], 0)
        self.assertEqual(step["body"]["service_location"]["location_type_id"], 8736)
        original = self.h.transport.request

        def request(method, path, body=None, query=None):
            status, payload_body = original(method, path, body, query)
            if method == "PATCH" and "service_locations" in path:
                return 204, None
            return status, payload_body

        self.h.transport.request = request
        done = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))
        self.h.transport.request = original
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["location_email"]["status"], "verified")
        self.assertEqual(done["readback"]["location_email"]["value"], "reports@example.test")
        self.assertEqual(done["readback"]["location_type_id"]["status"], "verified")
        self.assertEqual(done["readback"]["reminders_type"]["status"], "unverified")
        patches = [call for call in self.h.transport.calls if call["method"] == "PATCH" and "service_locations" in call["path"]]
        self.assertEqual(len(patches), 1)

        again = self.h.service.propose("create_customer", _home(last_name="Ambiguous", location_email="other@example.test", acknowledge_duplicate_coverage=["email"]), IDENTITY)
        self.assertTrue(again["ok"], again)
        original = self.h.transport.request

        def ambiguous(method, path, body=None, query=None):
            status, payload_body = original(method, path, body, query)
            if method == "PATCH" and "service_locations" in path:
                raise AmbiguousWriteError("timeout_after_apply")
            return status, payload_body

        self.h.transport.request = ambiguous
        reconciled = self.h.service.execute(again["proposal_id"], IDENTITY, operator_approval=self.h.approve(again["proposal_id"]))
        self.h.transport.request = original
        self.assertTrue(reconciled["ok"], reconciled)
        self.assertEqual(reconciled["readback"]["location_email"]["value"], "other@example.test")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "PATCH" and "service_locations" in call["path"]]), 2)

"""One-time services, status catalog, recurrence provenance, and contact creation. Offline only."""

from __future__ import annotations

import unittest

from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.fieldwork import parse_work_order_status_catalog, recurrence_provenance, resolve_work_order_status, service_active_eligibility, work_order_view
from tests.test_write_mcp import IDENTITY, Harness

TERMITE = "Termite Treatment"
FOLLOW = "Extra Service / Follow-up"


def _line(name: str, payable_id: int, price: int) -> dict:
    return {
        "name": name,
        "type": "service",
        "quantity": 1,
        "price": price,
        "payable_id": payable_id,
        "payable_type": "Service",
        "taxable": False,
    }


def _order(**extra: object) -> dict:
    payload = {
        "customer_id": 41,
        "service_location_id": 77,
        "repeat_type": "none",
        "repeat_period": 1,
        "starts_at": "2026-11-02",
        "duration": 45,
        "service_route_ids": [1],
        "instructions": "One visit. No agreement.",
    }
    payload.update(extra)
    return payload


class OneTimeGeneralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness(writes_enabled=True, api_role="writer")
        self.h.transport.users = [{
            "id": 10, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.test",
            "service_route_id": 1, "service_route_name": "North", "is_technician": True, "branches": [],
        }]
        self.h.transport.services.extend([
            {"id": 38812, "description": "German Roach Treatment - Initial", "price": "225.0", "site_time": None, "frequency": None},
            {"id": 38853, "description": TERMITE, "price": "900.0", "site_time": None, "frequency": None},
            {"id": 38804, "description": FOLLOW, "price": "0.0", "site_time": None, "frequency": None},
        ])

    def tearDown(self) -> None:
        self.h.close()

    def _propose(self, payload: dict) -> dict:
        return self.h.service.propose("create_work_order", payload, IDENTITY)

    def _execute(self, proposed: dict) -> dict:
        return self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval=self.h.approve(proposed["proposal_id"]))

    def test_termite_override_and_independent_production(self) -> None:
        proposed = self._propose(_order(
            starts_at="2026-11-03",
            line_items=[_line(TERMITE, 38853, 1275)],
            production_value=400,
        ))
        self.assertTrue(proposed["ok"], proposed)
        resolution = proposed["after"]["price_resolution"]
        self.assertEqual(resolution["catalog_price"], 900)
        self.assertEqual(resolution["final_price"], 1275)
        self.assertEqual(resolution["price_source"], "explicit_approved_override")
        self.assertTrue(resolution["override"])
        self.assertIsNone(resolution["observed_existing_work_order_price"])
        occurrence = proposed["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(occurrence["production_value"], 400)
        self.assertEqual(proposed["after"]["production_source"], "explicit_approved")
        self.assertNotEqual(occurrence["production_value"], 1275)
        self.assertEqual(occurrence["duration"], 45)
        self.assertNotEqual(occurrence["duration"], 60)
        self.assertEqual(proposed["after"]["active_eligibility"], "unverified")
        self.assertFalse(proposed["after"]["active_flag_fabricated"])
        self.assertEqual(proposed["after"]["service_record"]["unknowns"]["active"], "not_in_response")
        self.assertEqual(proposed["after"]["service_record"]["unknowns"]["production_default"], "not_in_response")
        self.assertIsNone(proposed["after"]["service_record"]["site_time"])
        self.assertTrue(proposed["after"]["service_record"]["site_time_present"])
        self.assertFalse(proposed["after"]["execution_blocked"])
        self.assertEqual(proposed["after"]["selectability_source"], "bt_services_index_matched_work_order_selector")
        self.assertFalse(proposed["after"]["list_membership_proves_active"])
        self.assertFalse(proposed["after"]["universal_api_guarantee"])
        self.assertIsNone(proposed["after"]["price_resolution"]["template_price"])
        self.assertFalse(proposed["after"]["template_consulted"])
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertFalse(done["live_tested"])
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        sent = posts[0]["body"]["service_appointment"]["line_items_attributes"][0]
        self.assertEqual(sent["price"], 1275)
        self.assertEqual(sent["payable_id"], 38853)
        self.assertEqual(posts[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]["production_value"], 400)

    def test_zero_price_callback_and_separate_production(self) -> None:
        callback = self._propose(_order(
            starts_at="2026-11-04",
            line_items=[_line(FOLLOW, 38804, 0)],
            production_value=0,
            callback=True,
        ))
        self.assertTrue(callback["ok"], callback)
        self.assertEqual(callback["after"]["price_source"], "catalog/default")
        self.assertEqual(callback["after"]["price"], 0)
        occurrence = callback["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(occurrence["production_value"], 0)
        self.assertIs(occurrence["callback"], True)
        self.assertEqual(callback["after"]["callback_source"], "explicit_approved")
        priced = self._propose(_order(
            starts_at="2026-11-05",
            line_items=[_line(FOLLOW, 38804, 0)],
            production_value=35,
            callback=False,
        ))
        self.assertEqual(priced["after"]["price"], 0)
        priced_occurrence = priced["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(priced_occurrence["production_value"], 35)
        self.assertIs(priced_occurrence["callback"], False)
        done = self._execute(priced)
        self.assertTrue(done["ok"], done)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        sent_occurrence = posts[0]["body"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertEqual(sent_occurrence["production_value"], 35)
        self.assertIs(sent_occurrence["callback"], False)
        self.assertEqual(posts[0]["body"]["service_appointment"]["line_items_attributes"][0]["price"], 0)

    def test_omitted_production_is_not_manufactured_and_generic_defaults_are_required(self) -> None:
        omitted = self._propose(_order(starts_at="2026-11-06", line_items=[_line(TERMITE, 38853, 900)]))
        self.assertTrue(omitted["ok"], omitted)
        occurrence = omitted["after"]["documented_request"]["service_appointment"]["appointment_occurrences_attributes"][0]
        self.assertNotIn("production_value", occurrence)
        self.assertEqual(omitted["after"]["production_source"], "omitted_remote_default_unverified")
        self.assertNotIn("callback", occurrence)
        payload = _order(starts_at="2026-11-07", line_items=[_line(TERMITE, 38853, 900)])
        payload.pop("duration")
        payload.pop("instructions")
        missing = self._propose(payload)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["gate"], "missing_field")
        self.assertEqual(missing["fields"], ["duration", "instructions"])

    def test_unknown_inactive_and_nonfinite_values_are_rejected(self) -> None:
        unknown = self._propose(_order(starts_at="2026-11-08", line_items=[_line("Missing", 99999, 10)]))
        self.assertEqual(unknown["reason"], "payable_not_in_services")
        self.h.transport.services.append({"id": 38899, "description": "Closed Service", "price": "10.0", "active": False})
        inactive = self._propose(_order(starts_at="2026-11-09", line_items=[_line("Closed Service", 38899, 10)], duration=30, instructions="no"))
        self.assertEqual(inactive["reason"], "service_inactive")
        self.assertEqual(inactive["active_eligibility"], "inactive")
        self.h.transport.services.append({"id": 38900, "description": "Mixed Flags", "price": "10.0", "active": True, "enabled": False})
        mixed = self._propose(_order(starts_at="2026-11-09T10:00:00-04:00", line_items=[_line("Mixed Flags", 38900, 10)], duration=30, instructions="no"))
        self.assertEqual(mixed["reason"], "service_eligibility_contradictory")
        self.assertEqual(mixed["active_eligibility"], "contradictory")
        self.h.transport.services.append({"id": 38901, "description": "Disabled Only", "price": "10.0", "enabled": False})
        disabled = self._propose(_order(starts_at="2026-11-09T11:00:00-04:00", line_items=[_line("Disabled Only", 38901, 10)], duration=30, instructions="no"))
        self.assertEqual(disabled["reason"], "service_inactive")
        self.assertEqual(service_active_eligibility({"active": True, "enabled": False}), "contradictory")
        self.assertEqual(service_active_eligibility({"enabled": False}), "inactive")
        self.assertEqual(service_active_eligibility({"disabled": True}), "inactive")
        self.assertEqual(service_active_eligibility({"active": True}), "explicit_true_not_proven_selectable")
        self.assertEqual(service_active_eligibility({}), "unverified")
        self.assertEqual(service_active_eligibility({"inactive": True, "active": False}), "inactive")
        self.assertEqual(service_active_eligibility({"deleted": False}), "unverified")
        self.assertEqual(service_active_eligibility({"archived": False}), "unverified")
        self.assertEqual(service_active_eligibility({"deleted": True}), "inactive")
        self.assertEqual(service_active_eligibility({"deleted": True, "active": True}), "contradictory")
        self.h.transport.services.append({"id": 38902, "description": "Deleted Service", "price": "10.0", "deleted": True})
        deleted = self._propose(_order(starts_at="2026-11-09T12:00:00-04:00", line_items=[_line("Deleted Service", 38902, 10)], duration=30, instructions="no"))
        self.assertEqual(deleted["reason"], "service_inactive")
        self.h.transport.services.append({"id": 38903, "description": "Archived Service", "price": "10.0", "archived": True})
        archived = self._propose(_order(starts_at="2026-11-09T13:00:00-04:00", line_items=[_line("Archived Service", 38903, 10)], duration=30, instructions="no"))
        self.assertEqual(archived["reason"], "service_inactive")
        self.h.transport.services.append({"id": 38904, "description": "Both Flags", "price": "10.0", "deleted": True, "active": True})
        both = self._propose(_order(starts_at="2026-11-09T14:00:00-04:00", line_items=[_line("Both Flags", 38904, 10)], duration=30, instructions="no"))
        self.assertEqual(both["reason"], "service_eligibility_contradictory")
        negative = self._propose(_order(line_items=[_line(TERMITE, 38853, -5)], starts_at="2026-11-10"))
        self.assertEqual(negative["fields"], ["price"])
        floated = self._propose(_order(line_items=[_line(TERMITE, 38853, 1.5)], starts_at="2026-11-11"))  # type: ignore[list-item]
        self.assertEqual(floated["fields"], ["price"])
        bad_production = self._propose(_order(production_value=-1, starts_at="2026-11-12", line_items=[_line(TERMITE, 38853, 900)]))
        self.assertEqual(bad_production["fields"], ["production_value"])

    def test_live_occurrence_omits_repeat_type_and_does_not_replay(self) -> None:
        self.h.transport.include_repeat_type_on_occurrence = False
        proposed = self._propose(_order(starts_at="2026-11-13"))
        failed = self._execute(proposed)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["reason"], "readback_failed")
        self.assertEqual(failed["partial"]["reason"], "repeat_type_unverified")
        self.assertEqual(failed["partial"]["field"], "repeat_type")
        self.assertFalse(failed["partial"]["field_checks"]["repeat_type"]["verified"])
        self.assertEqual(failed["partial"]["field_checks"]["repeat_type"]["authoritative_source"], "not_in_documented_get")
        self.assertTrue(failed["partial"]["field_checks"]["taxable"]["verified"])
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        occurrence_id = str(failed["partial"]["occurrence_id"])
        view = work_order_view(self.h.client.get_work_order(occurrence_id))
        self.assertFalse(view["recurrence"]["verified"])
        self.assertEqual(view["recurrence"]["reason"], "occurrence_get_omits_repeat_type")
        self.assertEqual(view["recurrence"]["bound_occurrence_id"], int(occurrence_id))
        self.assertNotEqual(view["recurrence"]["bound_service_appointment_id"], view["recurrence"]["bound_occurrence_id"])
        again = self.h.service.execute(proposed["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertNotEqual(again.get("ok"), True)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 1)
        self.assertFalse(any(call["method"] == "PATCH" and "/work_orders/" in call["path"] for call in self.h.transport.calls))

    def test_taxable_mismatch_stays_visible_when_repeat_type_is_missing(self) -> None:
        self.h.transport.include_repeat_type_on_occurrence = False
        self.h.transport.readback_taxable = True
        proposed = self._propose(_order(starts_at="2026-11-14"))
        failed = self._execute(proposed)
        self.assertFalse(failed["ok"])
        fields = {item["field"] for item in failed["partial"]["mismatches"]}
        self.assertIn("taxable", fields)
        unverified = {item["field"] for item in failed["partial"]["unverified"]}
        self.assertIn("repeat_type", unverified)
        self.assertEqual(failed["partial"]["field_checks"]["taxable"]["verified"], False)
        self.assertNotEqual(failed["partial"]["field_checks"]["repeat_type"]["verified"], True)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)

    def test_custom_status_catalog_resolves_value_not_i18n_key_or_id(self) -> None:
        entries = self.h.client.list_work_order_statuses()
        today = resolve_work_order_status(entries, "Today - Anytime")
        self.assertEqual(today["write"], "Today - Anytime")
        self.assertEqual(today["id"], 12501)
        missed = resolve_work_order_status(entries, "Missed Appointment")
        self.assertEqual(missed["write"], "Missed")
        self.assertEqual(missed["id"], 8011)
        self.assertEqual(self.h.transport.calls[-1]["path"], "/statuses")
        with self.assertRaises(GateError) as raised:
            parse_work_order_status_catalog(self.h.transport.i18n_statuses)
        self.assertEqual(raised.exception.gate, "work_order_status_catalog_unverified")
        with self.assertRaises(GateError) as ambiguous:
            resolve_work_order_status(parse_work_order_status_catalog([
                {"id": 1, "name": "Complete", "value": "Complete"},
                {"id": 2, "name": "Done", "value": "Complete"},
            ]), "Complete")
        self.assertEqual(ambiguous.exception.gate, "unknown_status")
        self.h.close()
        self.h = Harness(writes_enabled=True, api_role="writer", mapping_verified=True)
        self.h.transport.work_order_statuses = [{"id": 12501, "name": "Today - Anytime", "value": "Today - Anytime"}]
        self.h.transport.work_orders["8210"] = {
            "id": 8210,
            "service_appointment_id": 1501,
            "customer_id": 41,
            "service_location_id": 77,
            "status": "Scheduled",
            "starts_at": "2026-09-28T11:30:00-04:00",
            "starts_at_date": "2026-09-28",
            "duration": 60,
            "service_route_ids": [2557],
            "instructions": "gate",
            "repeat_type": "none",
            "production_value": "150.0",
            "line_items": [{"name": "PestGuard - Set-up", "price": "150.0", "quantity": 1, "payable_id": 38814, "payable_type": "Service", "taxable": False}],
        }
        numeric = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "12501"},
            IDENTITY,
        )
        self.assertEqual(numeric["gate"], "unknown_status")
        i18n_key = self.h.service.propose(
            "update_work_order_status",
            {"work_order_id": 8210, "service_appointment_id": 1501, "status": "missed_appointment"},
            IDENTITY,
        )
        self.assertEqual(i18n_key["gate"], "unknown_status")

    def test_contact_create_duplicate_wrong_customer_and_ambiguous_recovery(self) -> None:
        contact = {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.test", "phone": "7165550100"}
        proposed = self.h.service.propose("add_customer_contact", {"customer_id": 41, "contact": contact}, IDENTITY)
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["portal_access"], "not_sent")
        self.assertEqual(proposed["after"]["contact"]["email"], "ada@example.test")
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        self.assertEqual(done["readback"]["customer_id"], "41")
        self.assertEqual(done["readback"]["first_name"], "Ada")
        self.assertEqual(done["readback"]["last_name"], "Lovelace")
        self.assertEqual(done["readback"]["email"], "ada@example.test")
        self.assertEqual(done["readback"]["phone"], "7165550100")
        self.assertTrue(done["readback"]["field_checks"]["email"]["verified"])
        self.assertEqual(done["readback"]["authoritative_source"], "GET /v3.1/customers/{customer_id}/contacts")
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers/41/contacts"]
        self.assertEqual(len(posts), 1)
        self.assertNotIn("phone_kind", posts[0]["body"]["contact"])
        duplicate = self.h.service.propose("add_customer_contact", {"customer_id": 41, "contact": contact}, IDENTITY)
        self.assertEqual(duplicate["reason"], "contact_duplicate")
        self.assertEqual(len(posts), 1)

        other = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.test"}},
            IDENTITY,
        )
        original = self.h.transport.request

        def wrong_customer(method, path, body=None, query=None):
            status, payload = original(method, path, body, query)
            if method == "POST" and path == "/customers/41/contacts":
                for row in self.h.transport.contacts.values():
                    if row.get("email") == "grace@example.test":
                        row["customer_id"] = 999
            return status, payload

        self.h.transport.request = wrong_customer
        failed = self._execute(other)
        self.h.transport.request = original
        self.assertFalse(failed["ok"])
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers/41/contacts"]), 2)
        replay = self.h.service.execute(other["proposal_id"], IDENTITY, operator_approval="unused")
        self.assertNotEqual(replay.get("ok"), True)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers/41/contacts"]), 2)

        pending = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ken", "last_name": "Thompson", "email": "ken@example.test"}},
            IDENTITY,
        )
        self.h.transport.raise_after_exact.add("/customers/41/contacts")
        recovered = self._execute(pending)
        self.assertTrue(recovered["ok"], recovered)
        self.assertTrue(recovered["reconciled"])
        contact_posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/customers/41/contacts"]
        self.assertEqual(len(contact_posts), 3)

    def test_contact_preflight_blocks_whitespace_shared_email_and_late_duplicates(self) -> None:
        self.h.transport.contacts["41:91"] = {
            "id": 91,
            "customer_id": 41,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.test",
        }
        spaced = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ada ", "last_name": "Lovelace", "email": "Ada@Example.Test"}},
            IDENTITY,
        )
        self.assertFalse(spaced["ok"])
        self.assertEqual(spaced["reason"], "contact_duplicate")
        self.assertEqual(spaced["contact_id"], 91)
        self.assertFalse(spaced.get("merge", False))
        family = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Byron", "last_name": "Lovelace", "email": "ada@example.test"}},
            IDENTITY,
        )
        self.assertFalse(family["ok"])
        self.assertEqual(family["reason"], "shared_email_not_merged")
        self.assertEqual(family["gate"], "duplicate_unresolved")
        self.assertFalse(family["merge"])
        self.assertEqual(family["candidates"][0]["id"], 91)
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST"]), 0)

        fresh = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ada ", "last_name": "Lovelace", "email": "late@example.test"}},
            IDENTITY,
        )
        self.assertTrue(fresh["ok"], fresh)
        self.h.transport.contacts["41:92"] = {
            "id": 92,
            "customer_id": 41,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "late@example.test",
        }
        late = self._execute(fresh)
        self.assertFalse(late["ok"])
        self.assertEqual(late["reason"], "contact_duplicate")
        self.assertEqual(late["contact_id"], 92)
        self.assertFalse(late["merge"])
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and "/contacts" in call["path"]]), 0)

        renamed = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Grace", "last_name": "Hopper", "email": "grace2@example.test"}},
            IDENTITY,
        )
        self.h.transport.customers["41"]["name"] = "Renamed"
        changed = self._execute(renamed)
        self.assertEqual(changed["gate"], "identity_mismatch")
        self.assertEqual(changed["reason"], "customer_identity_changed")
        self.h.transport.customers["41"]["name"] = "Existing"
        self.h.transport.customers["41"]["customer_status"] = "Lead"
        lead = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ken", "last_name": "Thompson", "email": "lead@example.test"}},
            IDENTITY,
        )
        self.assertEqual(lead["gate"], "never_lead_status_accounts")
        self.h.transport.customers["41"]["customer_status"] = "Active"
        pending = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ken", "last_name": "Thompson", "email": "gone@example.test"}},
            IDENTITY,
        )
        self.assertTrue(pending["ok"], pending)
        self.h.transport.customers["41"]["customer_status"] = "Lead"
        became_lead = self._execute(pending)
        self.assertEqual(became_lead["gate"], "never_lead_status_accounts")
        self.h.transport.customers["41"]["customer_status"] = "Active"
        deleted_target = self.h.service.propose(
            "add_customer_contact",
            {"customer_id": 41, "contact": {"first_name": "Ken", "last_name": "Thompson", "email": "deleted@example.test"}},
            IDENTITY,
        )
        del self.h.transport.customers["41"]
        missing = self._execute(deleted_target)
        self.assertEqual(missing["gate"], "customer_not_found")
        self.assertEqual(missing["reason"], "customer_missing")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and "/contacts" in call["path"]]), 0)

    def test_generic_service_requires_its_own_repeat_period(self) -> None:
        payload = _order(starts_at="2026-11-16", line_items=[_line(TERMITE, 38853, 900)])
        payload.pop("repeat_period")
        missing = self._propose(payload)
        self.assertEqual(missing["fields"], ["repeat_period"])
        self.assertEqual(missing["reason"], "generic_service_repeat_period_required")

    def test_recurrence_provenance_does_not_treat_a_request_as_readback(self) -> None:
        absent = recurrence_provenance({"id": 50219749, "service_appointment_id": 8954306})
        self.assertFalse(absent["verified"])
        self.assertEqual(absent["authoritative_source"], "not_in_documented_get")
        self.assertEqual(absent["bound_occurrence_id"], 50219749)
        self.assertEqual(absent["bound_service_appointment_id"], 8954306)
        weekly = recurrence_provenance({"id": 1, "service_appointment_id": 2, "repeat_type": "weekly"})
        self.assertFalse(weekly["verified"])
        self.assertEqual(weekly["reason"], "recurrence_mismatch")
        found = self.h.client.search_services("Termite")
        self.assertEqual(found["items"][0]["id"], 38853)
        self.assertEqual(found["source"], "GET /v3.1/services")
        self.assertEqual(found["get_by_id"], "not_in_spec")
        one = self.h.client.get_service("38853")
        self.assertEqual(one["price"], "900.0")
        self.assertEqual(one["active_eligibility"], "unverified")

    def test_current_service_without_an_active_flag_uses_catalog_membership(self) -> None:
        invaders = "Pest Control - Occasional Invaders"
        self.h.transport.services.append({"id": 131844, "description": invaders, "price": "225.0"})
        proposed = self._propose(_order(
            starts_at="2026-11-22",
            duration=60,
            instructions="One visit.",
            line_items=[_line(invaders, 131844, 225)],
        ))
        self.assertTrue(proposed["ok"], proposed)
        self.assertEqual(proposed["after"]["price"], 225)
        self.assertEqual(proposed["after"]["price_source"], "catalog/default")
        self.assertEqual(proposed["after"]["standard_price"], 225)
        self.assertIsNone(proposed["after"]["price_resolution"]["observed_existing_work_order_price"])
        self.assertEqual(proposed["after"]["price_resolution"]["historical_work_order_price_role"], "not_catalog_evidence")
        self.assertEqual(proposed["after"]["active_eligibility"], "unverified")
        self.assertFalse(proposed["after"]["active_flag_fabricated"])
        self.assertFalse(proposed["after"]["execution_blocked"])
        self.assertIsNone(proposed["after"]["execution_block_reason"])
        self.assertEqual(proposed["after"]["catalog_membership"], "one_current_id_and_description")
        self.assertEqual(proposed["after"]["work_order_selectability"], "current_complete_catalog_member")
        self.assertEqual(proposed["after"]["catalog_equivalence"], "bt_account_180_ids_not_universal_api_guarantee")
        self.assertFalse(proposed["after"]["universal_api_guarantee"])
        self.assertFalse(proposed["after"]["list_membership_proves_active"])
        self.assertIn("neither source returned active, enabled, deleted, archived, or selectable", proposed["after"]["eligibility_evidence"])
        self.assertFalse(proposed["after"]["template_consulted"])
        done = self._execute(proposed)
        self.assertTrue(done["ok"], done)
        posts = [call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]
        self.assertEqual(len(posts), 1)
        sent = posts[0]["body"]["service_appointment"]["line_items_attributes"][0]
        self.assertEqual(sent["payable_id"], 131844)
        self.assertEqual(sent["name"], invaders)
        self.assertEqual(sent["price"], 225)
        self.assertEqual(sent["payable_type"], "Service")

    def test_name_mismatch_wrong_type_and_catalog_change_do_not_post(self) -> None:
        mismatch = self._propose(_order(starts_at="2026-11-23", line_items=[_line("Wrong Name", 38853, 900)]))
        self.assertEqual(mismatch["reason"], "caller_line_disagrees_with_service_catalog")
        material = _line(TERMITE, 38853, 900)
        material["payable_type"] = "Material"
        wrong_type = self._propose(_order(starts_at="2026-11-24", line_items=[material]))
        self.assertEqual(wrong_type["reason"], "caller_line_disagrees_with_template")
        unknown_type = _line(TERMITE, 38853, 900)
        unknown_type["payable_type"] = "Widget"
        rejected = self._propose(_order(starts_at="2026-11-25", line_items=[unknown_type]))
        self.assertEqual(rejected["gate"], "unknown_field")
        self.assertEqual(rejected["fields"], ["payable_type"])
        proposed = self._propose(_order(starts_at="2026-11-26", line_items=[_line(TERMITE, 38853, 900)]))
        self.assertTrue(proposed["ok"], proposed)
        for row in self.h.transport.services:
            if row.get("id") == 38853:
                row["price"] = "901.0"
        changed = self._execute(proposed)
        self.assertEqual(changed["gate"], "stale_state")
        self.assertEqual(changed["reason"], "service_catalog_changed")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 0)

    def test_incomplete_duplicate_and_failed_catalogs_do_not_post(self) -> None:
        self.h.transport.services.append({"id": 38853, "description": TERMITE, "price": "900.0"})
        duplicate = self._propose(_order(starts_at="2026-11-27", line_items=[_line(TERMITE, 38853, 900)]))
        self.assertEqual(duplicate["reason"], "service_id_conflict")
        self.h.transport.services.pop()
        original = self.h.client.list_services

        def incomplete():
            listed = original()
            listed["complete"] = False
            listed["truncated"] = True
            return listed

        self.h.client.list_services = incomplete
        partial = self._propose(_order(starts_at="2026-11-28", line_items=[_line(TERMITE, 38853, 900)]))
        self.assertEqual(partial["reason"], "service_list_incomplete")
        self.h.client.list_services = original
        request = self.h.transport.request

        def fail_catalog(method, path, body=None, query=None):
            if method == "GET" and path == "/services":
                return 500, {"error": "down"}
            return request(method, path, body, query)

        self.h.transport.request = fail_catalog
        failed = self._propose(_order(starts_at="2026-11-29", line_items=[_line(TERMITE, 38853, 900)]))
        self.h.transport.request = request
        self.assertFalse(failed["ok"])
        self.assertNotEqual(failed.get("reason"), "service_selectability_unverified")

        def malformed(method, path, body=None, query=None):
            if method == "GET" and path == "/services":
                return 200, {"not_a_list": True}
            return request(method, path, body, query)

        self.h.transport.request = malformed
        shape = self._propose(_order(starts_at="2026-11-30", line_items=[_line(TERMITE, 38853, 900)]))
        self.h.transport.request = request
        self.assertEqual(shape["gate"], "read_shape_unverified")
        self.h.transport.services.append({"id": 38910, "description": "Flagged True", "price": "10.0", "active": True})
        flagged = self._propose(_order(starts_at="2026-12-01", line_items=[_line("Flagged True", 38910, 10)], duration=30, instructions="no"))
        self.assertTrue(flagged["ok"], flagged)
        self.assertEqual(flagged["after"]["active_eligibility"], "explicit_true_not_proven_selectable")
        self.assertFalse(flagged["after"]["execution_blocked"])
        self.assertFalse(flagged["after"]["active_flag_fabricated"])
        proposed = self._propose(_order(starts_at="2026-12-02", line_items=[_line(TERMITE, 38853, 900)]))
        self.h.transport.services[:] = [row for row in self.h.transport.services if row.get("id") != 38853]
        removed = self._execute(proposed)
        self.assertEqual(removed["reason"], "payable_not_in_services")
        self.assertEqual(len([call for call in self.h.transport.calls if call["method"] == "POST" and call["path"] == "/work_orders"]), 0)


if __name__ == "__main__":
    unittest.main()
